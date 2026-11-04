import datetime
import os
import re
import threading
import time
import webbrowser

import wx

from . import prefs as prefs_mod
from .connection import Connection, PROTO_VERSION
from .i18n import GAME_MENU_CHOICE, LANGS, Tr
from . import dialogs
from .access import NamedAccessible
from .markup import Line, OutputParser
from .scripting import Aliases, Macros, Triggers, VAR_NAME, canonical_key, expand_vars
from . import creds
from .areamap import NoMap, fetch_rooms
from .chat import ChatStore
from .script import ScriptHost
from .sound import SoundPlayer, fetch_from_url, fetch_live_library
from .speech import Speech
from .telnet import Telnet
from . import updater
from .version import REPO, VERSION

_DIRS = {"kp8": "north", "kp2": "south", "kp4": "west", "kp6": "east", "kp9": "up", "kp1": "down"}
DEFAULT_KEYS = dict(_DIRS)
DEFAULT_KEYS.update({"alt+" + k: "scan " + d for k, d in _DIRS.items()})
DEFAULT_KEYS["kp5"] = "scan"

KEYPAD_CODES = {"kp%d" % i: 96 + i for i in range(10)}
KEYPAD_CODES.update({"kp*": 106, "kp+": 107, "kp-": 109, "kp.": 110, "kp/": 111})

THEMES = {
    "dark": ("#0d0b12", "#e3d8c0"),
    "light": ("#fbf8f1", "#1d1a14"),
}

PALETTE_DARK = {
    "fgdd": "#2e3436", "fgdr": "#cc0000", "fgdg": "#4e9a06", "fgdy": "#c4a000", "fgdb": "#3465a4",
    "fgdm": "#75507b", "fgdc": "#06989a", "fgdw": "#d3d7cf", "fgbd": "#555753", "fgbr": "#ed2330",
    "fgbg": "#8ee34f", "fgby": "#fdea56", "fgbb": "#55a3f2", "fgbm": "#d384cb", "fgbc": "#2cf4eb",
    "fgbw": "#ffffff", "fgbx": "#ffffff",
}

PALETTE_LIGHT = {
    "fgdd": "#2e3436", "fgdr": "#a40000", "fgdg": "#3a7304", "fgdy": "#7a6400", "fgdb": "#204a87",
    "fgdm": "#5c3566", "fgdc": "#04696b", "fgdw": "#4a4a46", "fgbd": "#555753", "fgbr": "#c4161f",
    "fgbg": "#2f7d10", "fgby": "#8a6d00", "fgbb": "#1f5fbf", "fgbm": "#8f3d87", "fgbc": "#00787a",
    "fgbw": "#000000", "fgbx": "#000000",
}

MAX_LINES = 20000
TRIM_LINES = 4000
HISTORY_MAX = 200
LINK_LIST_LINES = 300


class MainFrame(wx.Frame):
    def __init__(self, app_dir):
        self.app_dir = app_dir
        self.prefs = prefs_mod.load()
        if os.environ.get("DLCLIENT_QUIET"):
            self.prefs["sound"]["mute"] = True
            self.prefs["speech"] = False
        self.tr = Tr(self.prefs.get("lang", "en"))
        super().__init__(None, title=self.tr("app.title"), size=(900, 700))

        self.speech = Speech()
        live = os.path.join(prefs_mod.folder(), "sounds")
        self.sound = SoundPlayer(os.path.join(app_dir, "sounds"), self.prefs["sound"], live)
        self.sound_live = live
        self.sound_refreshed = 0.0
        self.sound.on_missing = self._sound_missing
        if not os.environ.get("DLCLIENT_QUIET"):
            self.sound_refreshed = time.time()
            threading.Thread(target=self._update_sounds, args=(live,), daemon=True).start()
        self.parser = OutputParser()
        self.find_text = ""
        self.find_row = None
        self.log_file = None
        self.palette = {}
        self.link_colour = None
        self.link_font = None
        self.telnet = Telnet()
        self.conn = Connection(self._frame_from_thread, self._state_from_thread)
        later = lambda secs, fn: wx.CallLater(int(secs * 1000), fn)
        self.triggers = Triggers(self.conn.rpc, later)
        self.macros = Macros(self.conn.rpc, later)
        self.aliases = Aliases(self.conn.rpc, self.conn.send_line, later)
        self.vars = self.prefs.setdefault("vars", {})
        self.settings_dlg = None
        chat_parser = OutputParser()
        self.chat = ChatStore(os.path.join(prefs_mod.folder(), "chat"),
                              lambda t: " ".join(l.text.strip() for l in chat_parser.parse(t)[0] if l.text.strip()))
        self.script = ScriptHost(
            send=lambda s: self.send_from_script(s),
            echo=lambda s: self.show_script_echo(s),
            notify=lambda s: self.script_notify(s),
            autobuff=lambda: self.conn.rpc("autobuff"),
            get_input=lambda: self.input.GetValue(),
            set_input=lambda s: self.input.ChangeValue(s),
            error=lambda s: self.notice(self.tr("script.error", s)),
            cache_dir=prefs_mod.folder(),
            bundled=os.path.join(app_dir, "dlclient", "defaults.js"),
        )
        self.script_asked = False
        if self.prefs.get("default_keys", True):
            self.script.load_stock()
        if not os.environ.get("DLCLIENT_QUIET"):
            threading.Thread(target=self._update_script, daemon=True).start()

        self.lines = [["", []]]
        self.echo_lines = set()
        self.history = list(self.prefs.get("history", []))[-HISTORY_MAX:]
        self.hist_pos = None
        self.hints = []
        self.hint_lines = {}
        self.hint_pos = None
        self.walk_until = 0
        self.walk_name = ""
        self.sound_fetching = set()
        self.completion = None
        self.prompt = {}
        self.prompt_due = False
        self.lang_answered = False
        self.lang_menu_waiting = False
        self.nanny_password = False
        self.auto_sent = set()

        self._build()
        self._build_menu()
        self.apply_theme()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.input.SetFocus()
        if self.prefs.get("log_session") and not os.environ.get("DLCLIENT_QUIET"):
            self.open_log()
        wx.CallAfter(self.connect)
        if updater.frozen() and self.prefs.get("check_updates", True) and not os.environ.get("DLCLIENT_QUIET"):
            wx.CallLater(5000, lambda: self.check_updates(quiet=True))

    def _build(self):
        panel = wx.Panel(self)
        self.panel = panel
        self.output = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_NOHIDESEL)
        self.input = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.password_mode = False
        self.output_acc = NamedAccessible(self.output, self.tr("output.name"))
        self.input_acc = NamedAccessible(self.input, self.tr("input.name"))

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(self.output, 1, wx.EXPAND)
        s.Add(self.input, 0, wx.EXPAND)
        panel.SetSizer(s)

        self.input.Bind(wx.EVT_TEXT_ENTER, self.on_enter)
        self.input.Bind(wx.EVT_KEY_DOWN, self.on_input_key)
        self.output.Bind(wx.EVT_KEY_DOWN, self.on_output_key)
        self.output.Bind(wx.EVT_CHAR, self.on_output_char)
        self.output.Bind(wx.EVT_CONTEXT_MENU, lambda e: self.line_menu(always_menu=True))

        accel = []
        for n in range(1, 11):
            ident = wx.NewIdRef()
            self.Bind(wx.EVT_MENU, lambda e, n=n: self.read_recent(n), id=ident)
            accel.append((wx.ACCEL_CTRL, ord(str(n % 10)), ident))
        for key, fn in ((wx.WXK_LEFT, lambda: self.chat_switch(-1)), (wx.WXK_RIGHT, lambda: self.chat_switch(1)),
                        (wx.WXK_UP, lambda: self.chat_move(-1)), (wx.WXK_DOWN, lambda: self.chat_move(1)),
                        (wx.WXK_END, lambda: self.chat_newest())):
            ident = wx.NewIdRef()
            self.Bind(wx.EVT_MENU, lambda e, fn=fn: fn(), id=ident)
            accel.append((wx.ACCEL_ALT, key, ident))
        for flags, key, fn in ((wx.ACCEL_CTRL, ord("="), lambda: self.change_font(1)),
                               (wx.ACCEL_CTRL, wx.WXK_NUMPAD_ADD, lambda: self.change_font(1)),
                               (wx.ACCEL_CTRL, ord("-"), lambda: self.change_font(-1)),
                               (wx.ACCEL_CTRL, wx.WXK_NUMPAD_SUBTRACT, lambda: self.change_font(-1))):
            ident = wx.NewIdRef()
            self.Bind(wx.EVT_MENU, lambda e, fn=fn: fn(), id=ident)
            accel.append((flags, key, ident))
        self.SetAcceleratorTable(wx.AcceleratorTable(accel))

    def _build_menu(self):
        tr = self.tr
        mb = wx.MenuBar()

        game = wx.Menu()
        self._item(game, tr("menu.connect"), lambda e: self.connect())
        self._item(game, tr("menu.disconnect"), lambda e: self.conn.disconnect())
        self._item(game, tr("menu.autologin"), lambda e: self.open_autologin())
        game.AppendSeparator()
        self._item(game, tr("menu.links"), lambda e: self.show_links())
        self._item(game, tr("menu.chat"), lambda e: self.open_chat())
        self._item(game, tr("menu.rooms"), lambda e: self.open_rooms())
        self._item(game, tr("menu.status"), lambda e: self.read_status())
        game.AppendSeparator()
        self._item(game, tr("menu.find"), lambda e: self.find_ask())
        self._item(game, tr("menu.findnext"), lambda e: self.find_step(-1))
        self._item(game, tr("menu.findprev"), lambda e: self.find_step(1))
        game.AppendSeparator()
        self._item(game, tr("menu.exit"), lambda e: self.Close())
        mb.Append(game, tr("menu.game"))

        opts = wx.Menu()
        lang = wx.Menu()
        for code, name in LANGS:
            it = lang.AppendRadioItem(wx.ID_ANY, name)
            it.Check(code == self.tr.lang)
            self.Bind(wx.EVT_MENU, lambda e, c=code: self.set_lang(c), it)
        opts.AppendSubMenu(lang, tr("menu.language"))
        it = opts.AppendCheckItem(wx.ID_ANY, tr("menu.speech"))
        it.Check(bool(self.prefs.get("speech")))
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_speech(), it)
        self.speech_item = it
        it = opts.AppendCheckItem(wx.ID_ANY, tr("menu.mute"))
        it.Check(bool(self.prefs["sound"].get("mute")))
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_mute(), it)
        self.mute_item = it
        it = opts.AppendCheckItem(wx.ID_ANY, tr("menu.echo"))
        it.Check(bool(self.prefs.get("echo", True)))
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_echo(), it)
        self.echo_item = it
        it = opts.AppendCheckItem(wx.ID_ANY, tr("menu.defkeys"))
        it.Check(bool(self.prefs.get("default_keys", True)))
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_default_keys(), it)
        self.defkeys_item = it
        it = opts.AppendCheckItem(wx.ID_ANY, tr("menu.hideprompt"))
        it.Check(bool(self.prefs.get("hide_prompt", True)))
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_hide_prompt(), it)
        self.hideprompt_item = it
        self._item(opts, tr("menu.volume_up"), lambda e: self.change_volume(10))
        self._item(opts, tr("menu.volume_down"), lambda e: self.change_volume(-10))
        self._item(opts, tr("menu.sound"), lambda e: self.open_sound())
        opts.AppendSeparator()
        look = wx.Menu()
        for code in ("dark", "light", "system"):
            it = look.AppendRadioItem(wx.ID_ANY, tr("theme." + code))
            it.Check(code == self.prefs.get("theme", "dark"))
            self.Bind(wx.EVT_MENU, lambda e, c=code: self.set_theme(c), it)
        look.AppendSeparator()
        it = look.AppendCheckItem(wx.ID_ANY, tr("menu.colors"))
        it.Check(bool(self.prefs.get("game_colors", True)))
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_colors(), it)
        self.colors_item = it
        self._item(look, tr("menu.font"), lambda e: self.choose_font())
        self._item(look, tr("font.bigger"), lambda e: self.change_font(1))
        self._item(look, tr("font.smaller"), lambda e: self.change_font(-1))
        opts.AppendSubMenu(look, tr("menu.appearance"))
        self._item(opts, tr("menu.speechfilter"), lambda e: self.open_speech_filter())
        self._item(opts, tr("menu.stopspeech"), lambda e: self.speech.silence())
        opts.AppendSeparator()
        it = opts.AppendCheckItem(wx.ID_ANY, tr("menu.log"))
        it.Check(bool(self.prefs.get("log_session")))
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_log(), it)
        self.log_item = it
        self._item(opts, tr("menu.logs"), lambda e: self.open_folder(self.logs_folder()))
        mb.Append(opts, tr("menu.options"))

        tools = wx.Menu()
        self._item(tools, tr("menu.triggers"), lambda e: self.open_tool("triggers"))
        self._item(tools, tr("menu.macros"), lambda e: self.open_tool("macros"))
        self._item(tools, tr("menu.aliases"), lambda e: self.open_tool("aliases"))
        self._item(tools, tr("menu.vars"), lambda e: self.open_tool("vars"))
        tools.AppendSeparator()
        self._item(tools, tr("menu.settings"), lambda e: self.open_settings())
        mb.Append(tools, tr("menu.tools"))

        hlp = wx.Menu()
        self._item(hlp, tr("menu.keys"), lambda e: self.show_text(tr("keys.title"), tr("keys.text")))
        self._item(hlp, tr("menu.credits"), lambda e: self.show_credits())
        hlp.AppendSeparator()
        self._item(hlp, tr("menu.updates"), lambda e: self.check_updates(quiet=False))
        it = hlp.AppendCheckItem(wx.ID_ANY, tr("menu.autoupdate"))
        it.Check(bool(self.prefs.get("check_updates", True)))
        self.Bind(wx.EVT_MENU, lambda e: self.prefs.__setitem__("check_updates", e.IsChecked()), it)
        self._item(hlp, tr("menu.folder"), lambda e: self.open_folder(prefs_mod.folder()))
        self._item(hlp, tr("menu.about"), lambda e: self.show_text(tr("about.title"), tr("about.text", VERSION, REPO)))
        mb.Append(hlp, tr("menu.help"))

        self.SetMenuBar(mb)

    def _item(self, menu, label, handler):
        it = menu.Append(wx.ID_ANY, label)
        self.Bind(wx.EVT_MENU, handler, it)
        return it

    def _update_script(self):
        try:
            text = self.script.fetch_stock()
        except Exception:
            return
        wx.CallAfter(self._stock_arrived, text)

    def _stock_arrived(self, text):
        if self.prefs.get("default_keys", True) and self.script.source == "stock" and text != self.script.text:
            self.script.load(text, "stock")

    def send_from_script(self, text):
        self.conn.send_line(self.aliases.expand(text))

    def show_script_echo(self, text):
        lines, complete, _ = self.parser.parse(text)
        if self.lines[-1][0]:
            self.append_lines([], True)
        self.append_lines(lines, complete)
        if self.prefs.get("speech"):
            self.speech.say("\n".join(l.text for l in lines if l.text.strip()))

    def script_notify(self, text):
        self.sound.play("ui/notify", {"T": "ui"})
        if not self.IsActive():
            self.RequestUserAttention()

    def _update_sounds(self, live, then=None):
        try:
            if fetch_live_library(live, os.path.join(self.app_dir, "sounds")):
                wx.CallAfter(self.sound.reload)
                if then:
                    wx.CallAfter(then)
        except Exception:
            pass

    def _sound_missing(self, kind, name, opts):
        url = (opts or {}).get("U")
        if url:
            full = url if url.lower().endswith((".mp3", ".ogg", ".wav")) else url.rstrip("/") + "/" + name
            if full in self.sound_fetching:
                return
            self.sound_fetching.add(full)

            def get():
                try:
                    got = fetch_from_url(full, self.sound_live, os.path.join(self.app_dir, "sounds"))
                except Exception:
                    got = None
                if got:
                    wx.CallAfter(self.sound.reload)
                    wx.CallAfter(self.sound.handle, kind, got, {k: v for k, v in opts.items() if k != "U"})
            threading.Thread(target=get, daemon=True).start()
            return
        if time.time() - self.sound_refreshed < 300:
            return
        self.sound_refreshed = time.time()
        replay = lambda: self.sound.resolve(name) and self.sound.handle(kind, name, opts)
        threading.Thread(target=self._update_sounds, args=(self.sound_live, replay), daemon=True).start()

    def connect(self):
        if self.conn.is_open:
            return
        self.conn.connect()

    def _frame_from_thread(self, command, args):
        wx.CallAfter(self.on_frame, command, args)

    def _state_from_thread(self, state, detail):
        wx.CallAfter(self.on_state, state, detail)

    def on_state(self, state, detail):
        if state == "connecting":
            self.notice(self.tr("state.connecting"))
        elif state == "closed":
            self.set_password_mode(False)
            self.notice(self.tr("state.closed"))
        elif state == "reconnecting" and detail == 1:
            self.notice(self.tr("state.reconnecting"))

    def on_frame(self, command, args):
        if command == "console_out" and args:
            self.on_console(str(args[0]))
        elif command == "nanny_step":
            step = args[0] if args else ""
            self.auto_login(step)
            self.nanny_password = step in ("password", "password_confirm")
            self.set_password_mode(self.nanny_password or self.telnet.echo_off)
        elif command == "version":
            self.conn.rpc("chat_subscribe", 1)
            self.auto_sent = set()
            self.nanny_password = False
            self.reset_lists()
            self.lang_answered = False
            self.lang_menu_waiting = False
            self.parser.msp_enabled = False
            self.telnet = Telnet()
            if args and args[0] != PROTO_VERSION:
                self.notice(self.tr("state.version", PROTO_VERSION, args[0]), speak=False)
            self.parser.nonce = args[1] if len(args) > 1 else None
        elif command == "msp":
            self.parser.msp_enabled = bool(args and args[0])
            if not self.parser.msp_enabled:
                self.sound.stop_all()
        elif command == "prompt" and args and isinstance(args[0], dict):
            self.prompt.update(args[0])
            self.prompt_due = True
            self.update_status()
            if self.nanny_password:
                self.nanny_password = False
                self.set_password_mode(self.telnet.echo_off)
            self.triggers.ask()
            self.macros.ask()
            self.aliases.ask()
            self.script.on_prompt(args[0])
            if not self.script_asked and self.conn.rpc("script_get"):
                self.script_asked = True
        elif command == "script_data" and args:
            if self.prefs.get("default_keys", True):
                self.script.on_script_data(args[0])
        elif command == "chat_state" and args and isinstance(args[0], dict):
            self.chat.set_who(args[0].get("who") or None)
        elif command == "chat" and args:
            self.chat.add(args[0])
        elif command == "config_state":
            self.reset_lists()
        elif command == "triggers_data" and args:
            self.triggers.on_data(args[0])
        elif command == "triggers_saved" and args:
            self.triggers.on_saved(args[0])
        elif command == "macros_data" and args:
            self.macros.on_data(args[0])
        elif command == "macros_saved" and args:
            self.macros.on_saved(args[0])
        elif command == "aliases_char" and args:
            self.aliases.on_char(args[0])
        elif command == "aliases_acct" and args:
            self.aliases.on_acct(args[0])
        elif command == "aliases_acct_saved" and args:
            self.aliases.on_saved(args[0])
        elif command in ("config_schema", "config_result", "config_changed") and args:
            dlg = self.settings_dlg
            if dlg:
                {"config_schema": dlg.on_schema, "config_result": dlg.on_result,
                 "config_changed": dlg.on_changed}[command](args[0])
        elif command == "resume_failed" and not self.conn.resume_pending:
            if self.lang_menu_waiting:
                self.answer_lang_menu()
        elif command == "alert" and args:
            self.notice(str(args[0]))

    def answer_lang_menu(self):
        self.lang_answered = True
        self.lang_menu_waiting = False
        self.conn.send_line(GAME_MENU_CHOICE.get(self.tr.lang, "1"))

    def on_console(self, raw):
        text = self.telnet.process(raw)
        self.set_password_mode(self.telnet.echo_off or self.nanny_password)
        if self.telnet.echo_off:
            self.auto_login("password")
        if not text:
            return
        if not self.lang_answered and "Choose your language" in text:
            if self.conn.resume_pending:
                self.lang_menu_waiting = True
            else:
                self.answer_lang_menu()
        lines, complete, msp = self.parser.parse(text)
        for kind, name, opts in msp:
            self.sound.handle(kind, name, opts)
        if self.prompt_due and not complete and lines and self.prefs.get("hide_prompt", True):
            lines[-1].text, lines[-1].links = "", []
        self.prompt_due = False
        starts = self.append_lines(lines, complete)
        self.run_triggers(lines, starts)
        if self.walk_until and time.time() < self.walk_until:
            head = "'%s'" % self.walk_name
            for line in lines:
                if line.text.strip().startswith(head) and line.links:
                    self.walk_until = 0
                    self.send_command("|".join(l.command for l in line.links if l.command))
                    break
        if self.prefs.get("speech"):
            skip = [w.lower() for w in self.prefs.get("speech_skip") or []]
            spoken = "\n".join(l.text for l in lines if l.text.strip() and l.text.strip() != ">"
                               and not any(w in l.text.lower() for w in skip))
            self.speech.say(spoken)

    def append_lines(self, lines, complete):
        if not lines and not complete:
            return []
        out = self.output
        reading = wx.Window.FindFocus() is out
        sel = out.GetSelection()
        base = out.GetLastPosition()
        starts = []
        chunks = []
        styles = []
        for i, line in enumerate(lines):
            if i > 0 and self.lines[-1][0]:
                self.lines.append(["", []])
                chunks.append("\n")
            cur = self.lines[-1]
            shift = len(cur[0])
            starts.append(base + sum(len(c) for c in chunks))
            text = line.text
            if not cur[0] and not text.strip():
                text = ""
            at = starts[-1]
            if self.palette:
                for a, b, cls in getattr(line, "colors", ()):
                    b = min(b, len(text))
                    colour = self.palette.get(cls)
                    if colour and b > a:
                        styles.append((at + a, at + b, colour, False))
            if self.link_colour:
                for l in line.links:
                    if l.end <= len(text):
                        styles.append((at + l.start, at + l.end, self.link_colour if not self.palette else None, True))
            for l in line.links:
                l.start += shift
                l.end += shift
            cur[0] += text
            cur[1].extend(line.links)
            chunks.append(text)
        if complete and self.lines[-1][0]:
            self.lines.append(["", []])
            chunks.append("\n")
        out.AppendText("".join(chunks))
        for a, b, colour, underline in styles:
            attr = wx.TextAttr()
            if colour:
                attr.SetTextColour(colour)
            if underline and self.link_font:
                attr.SetFont(self.link_font)
            out.SetStyle(a, b, attr)
        if self.log_file:
            try:
                self.log_file.write("".join(chunks))
                self.log_file.flush()
            except (OSError, ValueError):
                self.log_file = None
        if len(self.lines) > MAX_LINES:
            cut = sum(len(t) + 1 for t, _ in self.lines[:TRIM_LINES])
            del self.lines[:TRIM_LINES]
            alive = {id(l) for l in self.lines}
            self.echo_lines &= alive
            out.Remove(0, cut)
            sel = (max(0, sel[0] - cut), max(0, sel[1] - cut))
            starts = [max(0, x - cut) for x in starts]
        if reading:
            out.SetSelection(*sel)
        return starts

    def notice(self, text, speak=True):
        if self.lines[-1][0]:
            self.append_lines([], True)
        self.append_lines([Line(text, [])], True)
        if speak and self.prefs.get("speech"):
            self.speech.say(text)

    def echo(self, text):
        if not self.prefs.get("echo", True):
            return
        if self.lines[-1][0] and not self.lines[-1][0].endswith(" "):
            self.append_lines([Line(" ", [])], False)
        self.append_lines([Line(text, [])], True)
        if len(self.lines) > 1:
            self.echo_lines.add(id(self.lines[-2]))

    def current_line(self):
        pos = self.output.GetInsertionPoint()
        before = self.output.GetRange(0, pos)
        row = before.count("\n")
        col = pos - (before.rfind("\n") + 1)
        return min(row, len(self.lines) - 1), col

    def on_enter(self, event):
        text = self.input.GetValue()
        self.input.ChangeValue("")
        if self.password_mode:
            self.conn.send_line(text)
            return
        if text.startswith("#"):
            self.echo(text)
            self.hash_command(text)
        else:
            self.echo(text)
            if not self.script.on_input(text):
                self.send_command(text, expand=True, echo=False)
        if text.strip() and (not self.history or self.history[-1] != text):
            self.history.append(text)
            del self.history[:-HISTORY_MAX]
        self.hist_pos = None
        self.hint_pos = None

    def send_command(self, text, echo_text=None, expand=False, echo=True):
        if echo:
            self.echo(echo_text if echo_text is not None else text)
        if expand:
            text = self.aliases.expand(text)
        if not self.conn.send_line(text):
            self.notice(self.tr("state.closed"))

    def on_input_key(self, event):
        if self.password_mode:
            return event.Skip()
        if (event.GetKeyCode() == wx.WXK_SPACE and event.ControlDown()
                and not event.AltDown() and not event.ShiftDown()):
            self.complete_word()
            return
        if self.run_macro(event):
            return
        key = event.GetKeyCode()
        if key in (wx.WXK_UP, wx.WXK_DOWN) and not event.HasAnyModifiers() and self.browse_hints(key):
            return
        if key in (wx.WXK_UP, wx.WXK_DOWN) and not event.HasAnyModifiers():
            self.keep_draft()
            if not self.history:
                return
            if self.hist_pos is None:
                self.hist_pos = len(self.history)
            self.hist_pos += -1 if key == wx.WXK_UP else 1
            self.hist_pos = max(0, min(len(self.history), self.hist_pos))
            value = self.history[self.hist_pos] if self.hist_pos < len(self.history) else ""
            self.input.ChangeValue(value)
            self.input.SetInsertionPointEnd()
            return
        if key == wx.WXK_ESCAPE:
            if self.hint_pos is None:
                self.keep_draft()
            self.hint_pos = None
            self.input.ChangeValue("")
            self.hist_pos = None
            return
        event.Skip()

    def complete_word(self):
        value = self.input.GetValue()
        pos = self.input.GetInsertionPoint()
        st = self.completion
        if not (st and st["value"] == value and st["pos"] == pos):
            m = re.search(r"[\w'-]+$", value[:pos])
            if not m:
                self.say(self.tr("complete.none"))
                return
            prefix = m.group(0)
            low = prefix.lower()
            found, seen = [], {low}
            for text, _ in reversed(self.lines):
                for word in reversed(re.findall(r"\w[\w'-]*", text)):
                    w = word.lower()
                    if w.startswith(low) and w not in seen:
                        seen.add(w)
                        found.append(word)
            if not found:
                self.say(self.tr("complete.none"))
                return
            st = self.completion = {"start": m.start(), "prefix": prefix, "found": found, "i": -1}
        st["i"] += 1
        if st["i"] >= len(st["found"]):
            st["i"] = -1
            word = st["prefix"]
        else:
            word = st["found"][st["i"]]
        start, end = st["start"], pos
        new = value[:start] + word + value[end:]
        self.input.ChangeValue(new)
        self.input.SetInsertionPoint(start + len(word))
        st["value"], st["pos"] = new, start + len(word)
        self.say(word)

    def hint_commands(self):
        out, seen = [], set()
        self.hint_lines = {}
        for text, links in reversed(self.lines[-LINK_LIST_LINES:]):
            for l in reversed(links):
                if l.command and not l.menu and not l.url and l.command not in seen:
                    seen.add(l.command)
                    out.append(l.command)
                    self.hint_lines[l.command] = text.strip()
        return out

    def browse_hints(self, key):
        at_history_end = self.hist_pos is None or self.hist_pos >= len(self.history)
        if self.hint_pos is None:
            if key != wx.WXK_DOWN or self.input.GetValue() or not at_history_end:
                return False
            self.hints = self.hint_commands()
            if not self.hints:
                self.say(self.tr("links.empty"))
                return True
            self.hint_pos = 0
        elif self.input.GetValue() != self.hints[self.hint_pos]:
            self.hint_pos = None
            return False
        else:
            self.hint_pos += 1 if key == wx.WXK_DOWN else -1
            if self.hint_pos < 0:
                self.hint_pos = None
                self.input.ChangeValue("")
                self.say(self.tr("input.name"))
                return True
            self.hint_pos = min(self.hint_pos, len(self.hints) - 1)
        value = self.hints[self.hint_pos]
        self.input.ChangeValue(value)
        self.input.SetInsertionPointEnd()
        line = self.hint_lines.get(value, "")
        self.say(value + ". " + line if line and line != value else value)
        return True

    def auto_login(self, step):
        al = self.prefs.get("autologin") or {}
        name = (al.get("name") or "").strip()
        if not al.get("enabled") or not name or step in self.auto_sent:
            return
        if step == "name":
            self.auto_sent.add(step)
            self.notice(self.tr("al2.as", name))
            self.conn.send_line(name)
        elif step == "password" and "name" in self.auto_sent:
            password = creds.load(name)
            if password:
                self.auto_sent.add(step)
                self.conn.send_line(password)

    def open_autologin(self):
        al = self.prefs.setdefault("autologin", {"enabled": False, "name": ""})
        dlg = dialogs.AutoLoginDialog(self, self.tr, bool(al.get("enabled")), al.get("name", ""),
                                      bool(creds.load(al.get("name", ""))))
        if dlg.ShowModal() == wx.ID_OK:
            old = al.get("name", "")
            name = dlg.name.GetValue().strip()
            if dlg.forgotten or (old and old.lower() != name.lower()):
                creds.delete(old)
            if dlg.password.GetValue():
                creds.save(name, dlg.password.GetValue())
            al["name"] = name
            al["enabled"] = dlg.enabled.GetValue() and bool(creds.load(name))
            if not os.environ.get("DLCLIENT_QUIET"):
                prefs_mod.save(self.prefs)
            self.say(self.tr("al2.on", name) if al["enabled"] else self.tr("al2.off"))
        dlg.password.SetValue("")
        dlg.Destroy()
        self.input.SetFocus()

    def keep_draft(self):
        text = self.input.GetValue()
        if not text.strip():
            return
        if self.hist_pos is not None and self.hist_pos < len(self.history) and self.history[self.hist_pos] == text:
            return
        if text in self.history:
            self.history.remove(text)
        self.history.append(text)
        del self.history[:-HISTORY_MAX]
        if self.hist_pos is None:
            self.hist_pos = len(self.history) - 1
        else:
            self.hist_pos = min(self.hist_pos, len(self.history) - 1)

    def set_password_mode(self, on):
        if on == self.password_mode:
            return
        self.password_mode = on
        if not on:
            self.input.ChangeValue("")
        set_password_char(self.input, on)
        self.input_acc.name = self.tr("password.name" if on else "input.name")
        if on:
            self.input.ChangeValue("")

    def on_output_key(self, event):
        if self.run_macro(event):
            return
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not event.HasAnyModifiers():
            self.line_menu(always_menu=False)
            return
        event.Skip()

    def on_output_char(self, event):
        code = event.GetUnicodeKey()
        if code >= 32 and not event.ControlDown() and not event.AltDown():
            self.input.SetFocus()
            self.input.WriteText(chr(code))
            return
        event.Skip()

    def reset_lists(self):
        self.script_asked = False
        self.triggers.reset()
        self.macros.reset()
        self.aliases.reset()

    def run_triggers(self, lines, starts):
        texts = [l.text for l in lines]
        for t in texts:
            if t.strip():
                self.script.on_text(t)
        fired, highlights, notes = self.triggers.run(texts)
        for i, a, b, mode, colour in highlights:
            if i < len(starts):
                self.highlight(starts[i] + a, starts[i] + b, mode, colour)
        for pattern in notes:
            self.notice(self.tr("tr.slow", pattern))
        for trig, cmd, sound in fired:
            if sound and sound.get("name"):
                self.sound.play(sound["name"], {"V": sound.get("V", 100)})
            if cmd:
                ok = self.triggers.allow_command()
                if ok == "paused":
                    self.notice(self.tr("tr.flood"))
                elif ok:
                    self.conn.send_line(self.aliases.expand(cmd))

    def highlight(self, start, end, mode, colour):
        try:
            c = wx.Colour(colour)
        except Exception:
            return
        if not c.IsOk():
            return
        attr = wx.TextAttr()
        if mode == "line":
            bg = self.output.GetBackgroundColour()
            attr.SetBackgroundColour(wx.Colour((c.Red() + 3 * bg.Red()) // 4, (c.Green() + 3 * bg.Green()) // 4,
                                               (c.Blue() + 3 * bg.Blue()) // 4))
        else:
            attr.SetTextColour(c)
        self.output.SetStyle(start, end, attr)

    def run_macro(self, event):
        name = dialogs.key_from_event(event)
        if not name:
            return False
        cmd = None
        if self.macros.known:
            cmd = self.macros.command_for(name)
            if cmd is None:
                fallback = dialogs.key_fallback_from_event(event)
                if fallback:
                    cmd = self.macros.command_for(fallback)
        if cmd is None and self.prefs.get("default_keys", True):
            if self.script.ctx and event.GetKeyCode() != wx.WXK_ESCAPE:
                numpad = dialogs._numpad_table().get(event.GetKeyCode())
                which, code = event.GetRawKeyCode(), ""
                if numpad:
                    which = KEYPAD_CODES.get(numpad, which)
                    code = "Numpad" + numpad[2:] if numpad[2:].isdigit() else ""
                if self.script.on_key(which, code, event.ControlDown(),
                                      event.AltDown(), event.ShiftDown()):
                    return True
            elif not self.script.ctx:
                cmd = DEFAULT_KEYS.get(name)
        if cmd is None:
            return False
        line = expand_vars(cmd, self.vars)
        self.send_command(line, expand=True)
        return True

    def hash_command(self, text):
        body = text[1:].strip()
        word, _, rest = body.partition(" ")
        rest = rest.strip()
        low = word.lower()
        if word.isdigit():
            n = min(int(word), 100)
            for _ in range(n):
                self.conn.send_line(self.aliases.expand(rest))
            return
        if low in ("var", "переменная", "змінна"):
            return self.hash_var(rest)
        if low in ("hotkey", "кнопка", "клавіша"):
            return self.hash_hotkey(rest)
        self.notice(self.tr("hash.unknown"))

    def hash_var(self, rest):
        parts = rest.split()
        if not parts:
            if not self.vars:
                return self.notice(self.tr("hash.var.empty"))
            return self.notice(self.tr("hash.var.list") + "\n" +
                               "\n".join("    %s : %s" % kv for kv in sorted(self.vars.items())))
        name = parts[0]
        if len(parts) == 1:
            if name in self.vars:
                return self.notice("$%s : %s" % (name, self.vars[name]))
            return self.notice(self.tr("hash.var.none"))
        if len(parts) == 2 and parts[1] in ("delete", "удалить", "видалити"):
            if self.vars.pop(name, None) is None:
                return self.notice(self.tr("hash.var.none"))
            return self.notice(self.tr("hash.var.deleted", name))
        if not VAR_NAME.match(name):
            return self.notice(self.tr("var.badname"))
        self.vars[name] = " ".join(parts[1:])
        self.notice(self.tr("hash.var.set", name, self.vars[name]))

    def hash_hotkey(self, rest):
        if not self.macros.known:
            return self.notice(self.tr("hash.wait"))
        parts = rest.split(None, 1)
        if not parts:
            rows = self.macros.all()
            if not rows:
                return self.notice(self.tr("hash.hotkey.empty"))
            return self.notice(self.tr("hash.hotkey.list") + "\n" + "\n".join(
                "    %s : %s (%s)" % (m["key"], m["cmd"], self.tr("scope." + sc)) for sc, m in rows))
        key = canonical_key(parts[0])
        arg = parts[1].strip() if len(parts) > 1 else ""
        if arg in ("delete", "удалить", "видалити"):
            found = False
            for scope in ("char", "acct"):
                lst = self.macros.lists[scope]
                if any(m["key"] == key for m in lst):
                    found = True
                    self.macros.set_list(scope, [m for m in lst if m["key"] != key])
            return self.notice(self.tr("hash.hotkey.deleted" if found else "hash.hotkey.none", key))
        if not key:
            return self.notice(self.tr("hash.hotkey.badkey", parts[0]))
        if not arg:
            rows = [(sc, m) for sc, m in self.macros.all() if m["key"].startswith(key)]
            if not rows:
                return self.notice(self.tr("hash.hotkey.none"))
            return self.notice("\n".join("    %s : %s (%s)" % (m["key"], m["cmd"], self.tr("scope." + sc))
                                         for sc, m in rows))
        scope = "acct" if self.macros.account else "char"
        lst = [m for m in self.macros.lists[scope] if m["key"] != key]
        if len(lst) >= self.macros.max_items:
            return self.notice(self.tr("list.full"))
        self.macros.set_list(scope, lst + [{"key": key, "cmd": arg}])
        self.notice(self.tr("hash.hotkey.set", key, arg))

    def open_tool(self, which):
        if which == "triggers":
            dlg = dialogs.TriggersDialog(self, self.tr, self.triggers, self.sound)
        elif which == "macros":
            dlg = dialogs.MacrosDialog(self, self.tr, self.macros, lambda t: self.say(t))
        elif which == "aliases":
            dlg = dialogs.AliasesDialog(self, self.tr, self.aliases)
        else:
            dlg = dialogs.VarsDialog(self, self.tr, self.vars)
        dlg.ShowModal()
        dlg.Destroy()
        self.input.SetFocus()

    def open_settings(self):
        dlg = dialogs.SettingsDialog(self, self.tr, self.conn.rpc, lambda t: self.say(t))
        self.settings_dlg = dlg
        if not self.conn.in_world or not self.conn.rpc("config_schema"):
            dlg.set_waiting(self.tr("cfg.wait"))
        else:
            wx.CallLater(2500, lambda: dlg and not dlg.pages and dlg.set_waiting(self.tr("cfg.missing"))
                         if self.settings_dlg is dlg else None)
        dlg.ShowModal()
        self.settings_dlg = None
        dlg.Destroy()
        self.input.SetFocus()

    def line_menu(self, always_menu):
        row, col = self.current_line()
        links = self.lines[row][1]
        if not links:
            self.say(self.tr("links.none"))
            return
        under = [l for l in links if l.start <= col < l.end]
        if not always_menu:
            if under and not under[0].menu:
                return self.activate(under[0])
            if len(links) == 1 and not links[0].menu:
                return self.activate(links[0])
            if len(under) == 1 and under[0].menu:
                return self.popup_item_menu(under[0])
        menu = wx.Menu()
        for l in links:
            if l.menu:
                sub = self._item_submenu(l)
                menu.AppendSubMenu(sub, l.label)
            else:
                it = menu.Append(wx.ID_ANY, self.link_title(l))
                self.Bind(wx.EVT_MENU, lambda e, l=l: self.activate(l), it)
        self.PopupMenu(menu)
        menu.Destroy()

    def link_title(self, l):
        if l.url:
            return l.label
        if l.command and l.command != l.label:
            return "%s: %s" % (l.label, l.command)
        return l.label

    def _item_submenu(self, l):
        sub = wx.Menu()
        for entry in l.menu:
            if entry is None:
                sub.AppendSeparator()
                continue
            label, cmd = entry
            it = sub.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda e, c=cmd: self.send_command(c), it)
        return sub

    def popup_item_menu(self, l):
        sub = self._item_submenu(l)
        self.PopupMenu(sub)
        sub.Destroy()

    def activate(self, l):
        if l.url:
            self.say(self.tr("links.open", l.url))
            webbrowser.open(l.url)
            return
        if l.menu:
            return self.popup_item_menu(l)
        if l.confirm:
            dlg = wx.MessageDialog(self, self.tr("confirm.craft"), self.tr("confirm.title"),
                                   wx.YES_NO | wx.NO_DEFAULT)
            ok = dlg.ShowModal() == wx.ID_YES
            dlg.Destroy()
            if not ok:
                return
        self.send_command(l.command)

    def show_links(self):
        found = []
        for text, links in reversed(self.lines[-LINK_LIST_LINES:]):
            for l in reversed(links):
                found.append(l)
        if not found:
            self.say(self.tr("links.empty"))
            return
        dlg = LinksDialog(self, self.tr, [self.link_title(l) for l in found])
        if dlg.ShowModal() == wx.ID_OK and dlg.choice is not None:
            l = found[dlg.choice]
            dlg.Destroy()
            self.input.SetFocus()
            self.activate(l)
        else:
            dlg.Destroy()

    def update_status(self):
        p = self.prompt
        if "hit" in p:
            title = "%s - %s/%shp %s/%smn %s/%smv" % (self.tr("app.title"), p.get("hit"), p.get("max_hit"),
                                                     p.get("mana"), p.get("max_mana"), p.get("move"), p.get("max_move"))
            if title != self.GetTitle():
                self.SetTitle(title)

    def status_text(self):
        p = self.prompt
        if "hit" not in p:
            return self.tr("status.none")
        s = self.tr("status.line", p.get("hit"), p.get("max_hit"), p.get("mana"),
                    p.get("max_mana"), p.get("move"), p.get("max_move"))
        if p.get("fight"):
            s += " " + self.tr("status.fighting")
        return s

    def buffer_label(self, name):
        key = "chat.buf." + name
        label = self.tr(key)
        return name if label == key else label

    def chat_switch(self, step):
        name = self.chat.switch(step)
        n = len(self.chat.buffer_rows())
        self.say(self.tr("chat.switched", self.buffer_label(name), n))

    def chat_move(self, step):
        row, edge = self.chat.move(step)
        if edge == "empty":
            return self.say(self.tr("chat.empty"))
        text = row.get("text", "")
        if edge == "top":
            text = self.tr("chat.top") + " " + text
        elif edge == "end":
            text = self.tr("chat.end") + " " + text
        self.say(text)

    def chat_newest(self):
        row = self.chat.newest()
        self.say(row.get("text", "") if row else self.tr("chat.empty"))

    def open_chat(self):
        dlg = dialogs.ChatDialog(self, self.tr, self.chat, self.buffer_label)
        dlg.ShowModal()
        dlg.Destroy()
        self.input.SetFocus()

    def open_rooms(self):
        area = self.prompt.get("area")
        if not area:
            return self.say(self.tr("rooms.nowhere"))
        self.say(self.tr("rooms.loading"))
        lang = self.tr.lang

        def load():
            try:
                rooms = fetch_rooms(area, lang)
            except NoMap:
                rooms = None
            except Exception:
                rooms = False
            wx.CallAfter(self._rooms_loaded, rooms)
        threading.Thread(target=load, daemon=True).start()

    def _rooms_loaded(self, rooms):
        if rooms is None:
            return self.say(self.tr("rooms.nomap"))
        if rooms is False:
            return self.say(self.tr("rooms.offline"))
        dlg = dialogs.RoomsDialog(self, self.tr, rooms)
        if dlg.ShowModal() == wx.ID_OK and dlg.choice:
            vnum, how, self.walk_name = dlg.choice
            self.walk_until = time.time() + 5 if how == dlg.WALK else 0
            self.send_command("path %d" % vnum)
        dlg.Destroy()
        self.input.SetFocus()

    def read_recent(self, n):
        seen = 0
        for line in reversed(self.lines):
            t = line[0].strip()
            if not t or t == ">" or id(line) in self.echo_lines:
                continue
            seen += 1
            if seen == n:
                return self.say(t)
        self.say(self.tr("recent.none"))

    def read_status(self):
        self.say(self.status_text(), interrupt=True)

    def say(self, text, interrupt=True):
        self.speech.say(text, interrupt=interrupt)

    def toggle_speech(self):
        self.prefs["speech"] = not self.prefs.get("speech")
        self.speech_item.Check(self.prefs["speech"])
        self.say(self.tr("speech.on" if self.prefs["speech"] else "speech.off"))

    def toggle_echo(self):
        self.prefs["echo"] = not self.prefs.get("echo", True)
        self.echo_item.Check(self.prefs["echo"])
        self.say(self.tr("echo.on" if self.prefs["echo"] else "echo.off"))

    def toggle_hide_prompt(self):
        self.prefs["hide_prompt"] = not self.prefs.get("hide_prompt", True)
        self.hideprompt_item.Check(self.prefs["hide_prompt"])
        self.say(self.tr("hideprompt.on" if self.prefs["hide_prompt"] else "hideprompt.off"))

    def toggle_default_keys(self):
        self.prefs["default_keys"] = not self.prefs.get("default_keys", True)
        self.defkeys_item.Check(self.prefs["default_keys"])
        if self.prefs["default_keys"]:
            self.script.load_stock()
            self.script_asked = False
        else:
            self.script.ctx = None
        self.say(self.tr("defkeys.on" if self.prefs["default_keys"] else "defkeys.off"))

    def toggle_mute(self):
        s = self.prefs["sound"]
        s["mute"] = not s.get("mute")
        self.mute_item.Check(s["mute"])
        if s["mute"]:
            self.sound.stop_all()
        self.say(self.tr("sound.muted" if s["mute"] else "sound.unmuted"))

    def change_volume(self, delta):
        s = self.prefs["sound"]
        s["master"] = max(0, min(100, s.get("master", 80) + delta))
        self.say(self.tr("sound.volume", s["master"]))
        self.sound.play("ui/click", {"T": "ui"})

    def set_lang(self, code):
        if code == self.tr.lang:
            return
        self.prefs["lang"] = code
        self.tr = Tr(code)
        self._build_menu()
        self.output_acc.name = self.tr("output.name")
        self.input_acc.name = self.tr("password.name" if self.password_mode else "input.name")
        self.say(self.tr("lang.later"))

    def show_text(self, title, text):
        dlg = TextDialog(self, title, text, self.tr("ok"))
        dlg.ShowModal()
        dlg.Destroy()

    def show_credits(self):
        rows = []
        lang = self.tr.lang
        for s in self.sound.library:
            label = (s.get("label") or {}).get(lang) or s.get("name")
            rows.append("%s: \"%s\" by %s, %s. %s" % (label, s.get("title", ""), s.get("author", ""),
                                                     s.get("license", ""), s.get("source", "")))
        self.show_text(self.tr("credits.title"), "\n".join(rows))

    def apply_theme(self, recolour=True):
        theme = self.prefs.get("theme", "dark")
        if theme in THEMES:
            bg, fg = (wx.Colour(c) for c in THEMES[theme])
        else:
            bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        dark = (bg.Red() * 299 + bg.Green() * 587 + bg.Blue() * 114) / 1000 < 128
        palette = PALETTE_DARK if dark else PALETTE_LIGHT
        self.palette = {k: wx.Colour(v) for k, v in palette.items()} if self.prefs.get("game_colors", True) else {}
        self.link_colour = wx.Colour("#7fb6ff" if dark else "#1f5fbf")
        f = self.prefs.get("font") or {}
        font = wx.Font(wx.FontInfo(int(f.get("size", 12))).FaceName(f.get("face") or "Consolas"))
        if not font.IsOk():
            font = wx.Font(wx.FontInfo(int(f.get("size", 12))).Family(wx.FONTFAMILY_TELETYPE))
        self.link_font = font.Underlined()
        for ctrl in (self.output, self.input):
            ctrl.SetBackgroundColour(bg)
            ctrl.SetForegroundColour(fg)
            ctrl.SetFont(font)
        self.panel.SetBackgroundColour(bg)
        base = wx.TextAttr(fg, bg, font)
        self.output.SetDefaultStyle(base)
        last = self.output.GetLastPosition()
        if last:
            if recolour:
                self.output.SetStyle(0, last, base)
            else:
                only_font = wx.TextAttr()
                only_font.SetFont(font)
                self.output.SetStyle(0, last, only_font)
        self.input.SetDefaultStyle(base)
        self.output.Refresh()
        self.input.Refresh()

    def set_theme(self, code):
        self.prefs["theme"] = code
        self.apply_theme()
        self.say(self.tr("theme." + code).replace("&", ""))

    def toggle_colors(self):
        self.prefs["game_colors"] = not self.prefs.get("game_colors", True)
        self.colors_item.Check(self.prefs["game_colors"])
        self.apply_theme()
        self.say(self.tr("colors.on" if self.prefs["game_colors"] else "colors.off"))

    def choose_font(self):
        data = wx.FontData()
        data.SetInitialFont(self.output.GetFont())
        data.EnableEffects(False)
        dlg = wx.FontDialog(self, data)
        if dlg.ShowModal() == wx.ID_OK:
            font = dlg.GetFontData().GetChosenFont()
            self.prefs["font"] = {"face": font.GetFaceName(), "size": font.GetPointSize()}
            self.apply_theme(recolour=False)
        dlg.Destroy()
        self.input.SetFocus()

    def change_font(self, step):
        f = self.prefs.setdefault("font", {"face": "Consolas", "size": 12})
        f["size"] = max(7, min(40, int(f.get("size", 12)) + step))
        self.apply_theme(recolour=False)
        self.say(self.tr("font.size", f["size"]))

    def open_sound(self):
        dlg = dialogs.SoundDialog(self, self.tr, self.prefs["sound"], self.sound)
        dlg.ShowModal()
        dlg.Destroy()
        self.mute_item.Check(bool(self.prefs["sound"].get("mute")))
        self.input.SetFocus()

    def open_speech_filter(self):
        dlg = dialogs.SpeechFilterDialog(self, self.tr, self.prefs.get("speech_skip") or [])
        if dlg.ShowModal() == wx.ID_OK:
            self.prefs["speech_skip"] = dlg.words()
        dlg.Destroy()
        self.input.SetFocus()

    def logs_folder(self):
        path = os.path.join(prefs_mod.folder(), "logs")
        os.makedirs(path, exist_ok=True)
        return path

    def open_log(self):
        name = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S") + ".txt"
        path = os.path.join(self.logs_folder(), name)
        try:
            self.log_file = open(path, "a", encoding="utf-8", newline="\r\n")
        except OSError:
            self.log_file = None
            return None
        return path

    def toggle_log(self):
        self.prefs["log_session"] = not self.prefs.get("log_session")
        self.log_item.Check(self.prefs["log_session"])
        if self.prefs["log_session"]:
            path = self.open_log()
            if path:
                self.say(self.tr("log.on", os.path.basename(path)))
        else:
            if self.log_file:
                self.log_file.close()
            self.log_file = None
            self.say(self.tr("log.off"))

    def open_folder(self, path):
        try:
            os.startfile(path)
        except OSError:
            pass

    def find_ask(self):
        dlg = dialogs.FindDialog(self, self.tr, self.find_text)
        ok = dlg.ShowModal() == wx.ID_OK
        text = dlg.text.GetValue().strip()
        dlg.Destroy()
        if not ok or not text:
            self.input.SetFocus()
            return
        self.find_text = text
        self.find_row = None
        self.find_step(-1)

    def find_step(self, direction):
        if not self.find_text:
            return self.say(self.tr("find.first"))
        needle = self.find_text.lower()
        if self.find_row is None or self.find_row >= len(self.lines):
            row = len(self.lines)
        else:
            row = self.find_row
        row += direction
        while 0 <= row < len(self.lines):
            text = self.lines[row][0]
            col = text.lower().find(needle)
            if col >= 0 and id(self.lines[row]) not in self.echo_lines:
                self.find_row = row
                pos = sum(len(t) + 1 for t, _ in self.lines[:row]) + col
                self.output.SetFocus()
                self.output.SetInsertionPoint(pos)
                self.output.ShowPosition(pos)
                return self.say(text.strip())
            row += direction
        self.say(self.tr("find.none", self.find_text))

    def check_updates(self, quiet):
        if not quiet:
            self.say(self.tr("upd.checking"))

        def work():
            try:
                info = updater.latest()
            except Exception as e:
                if not quiet:
                    wx.CallAfter(self.notice, self.tr("upd.fail", e))
                return
            wx.CallAfter(self._update_found, info, quiet)
        threading.Thread(target=work, daemon=True).start()

    def _update_found(self, info, quiet):
        if not info.get("tag") or not updater.is_newer(info["tag"]):
            if not quiet:
                self.notice(self.tr("upd.none", VERSION))
            return
        dlg = wx.MessageDialog(self, self.tr("upd.ask", info["tag"].lstrip("v"), VERSION, info["notes"].strip()),
                               self.tr("upd.title"), wx.YES_NO | wx.YES_DEFAULT | wx.ICON_INFORMATION)
        yes = dlg.ShowModal() == wx.ID_YES
        dlg.Destroy()
        self.input.SetFocus()
        if not yes:
            return
        if not updater.frozen() or not info.get("url"):
            self.notice(self.tr("upd.source"))
            if info.get("page"):
                webbrowser.open(info["page"])
            return
        self.notice(self.tr("upd.downloading"))
        last = [0]

        def progress(pct):
            if pct >= last[0] + 25:
                last[0] = pct
                wx.CallAfter(self.say, self.tr("upd.progress", pct), False)

        def work():
            try:
                folder, root = updater.download(info["url"], progress)
            except Exception as e:
                wx.CallAfter(self.notice, self.tr("upd.fail", e))
                return
            wx.CallAfter(self._install_update, folder, root)
        threading.Thread(target=work, daemon=True).start()

    def _install_update(self, folder, root):
        try:
            updater.apply_and_restart(folder, root)
        except Exception as e:
            return self.notice(self.tr("upd.fail", e))
        self.Close()

    def on_close(self, event):
        if self.log_file:
            try:
                self.log_file.close()
            except OSError:
                pass
            self.log_file = None
        self.prefs["history"] = self.history[-HISTORY_MAX:]
        if not os.environ.get("DLCLIENT_QUIET"):
            try:
                prefs_mod.save(self.prefs)
            except OSError:
                pass
        self.conn.disconnect()
        self.sound.stop_all()
        event.Skip()


EM_SETPASSWORDCHAR = 0xCC


def set_password_char(ctrl, on):
    try:
        import ctypes
        hwnd = ctrl.GetHandle()
        ctypes.windll.user32.SendMessageW(hwnd, EM_SETPASSWORDCHAR, 0x25CF if on else 0, 0)
        ctrl.Refresh()
    except Exception:
        pass


class LinksDialog(wx.Dialog):
    def __init__(self, parent, tr, items):
        super().__init__(parent, title=tr("links.title"), size=(600, 450))
        self.choice = None
        label = wx.StaticText(self, label=tr("links.label"))
        self.list = wx.ListBox(self, choices=items)
        self.list.SetName(tr("links.label"))
        self.list.SetSelection(0)
        ok = wx.Button(self, wx.ID_OK, tr("ok"))
        cancel = wx.Button(self, wx.ID_CANCEL, tr("cancel"))
        ok.SetDefault()
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(label, 0, wx.ALL, 6)
        s.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)
        b = wx.StdDialogButtonSizer()
        b.AddButton(ok)
        b.AddButton(cancel)
        b.Realize()
        s.Add(b, 0, wx.ALL | wx.ALIGN_RIGHT, 6)
        self.SetSizer(s)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_ok)
        ok.Bind(wx.EVT_BUTTON, self.on_ok)
        self.list.SetFocus()

    def on_ok(self, event):
        self.choice = self.list.GetSelection() if self.list.GetSelection() != wx.NOT_FOUND else None
        self.EndModal(wx.ID_OK)


class TextDialog(wx.Dialog):
    def __init__(self, parent, title, text, ok_label):
        super().__init__(parent, title=title, size=(650, 450))
        t = wx.TextCtrl(self, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        t.SetName(title)
        ok = wx.Button(self, wx.ID_OK, ok_label)
        ok.SetDefault()
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(t, 1, wx.EXPAND | wx.ALL, 6)
        s.Add(ok, 0, wx.ALL | wx.ALIGN_RIGHT, 6)
        self.SetSizer(s)
        self.SetEscapeId(wx.ID_OK)
        t.SetFocus()
