import base64
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
from .areamap import MARKET_SQUARE, MIDGAARD, NoMap, area_key, fetch_areas, fetch_graph, fetch_rooms
from .mapview import AreaMap
from .helpsearch import HelpSearch
from . import status as status_mod
from .scripting import new_id
from .presence import classify, kind_of
from . import textlists
from . import framelists
from . import sitedata
from .guide import GuideDialog

AREA_WALK, AREA_ROUTE = "walk", "route"


def match_area(areas, names):
    """The area whose name in any language is one of names (lower case)."""
    for n in names:
        for a in areas:
            full = a["name"].lower()
            if n in (a["en"].lower(), a["ru"].lower(), full) or full.startswith(n + ", "):
                return a
    return None
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
        if self.prefs.get("server"):
            self.conn.url = self.prefs["server"]
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
        self.walk_then = None
        self.tone_room = None
        self.room_lines = []
        self.room_wait = None
        self.room_timer = None
        self.capture = None
        self.items_dlg = None
        self.items_view = None
        self.refresh_wait = 0
        self.help_search = HelpSearch(prefs_mod.folder())
        self.autobuff_dlg = None
        self.account_wait = None
        self.guide_dlg = None
        self.guide_keep = None
        self.guide_asked = False
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
        for n, (key, _fn) in enumerate(status_mod.PANELS, start=1):
            ident = wx.NewIdRef()
            self.Bind(wx.EVT_MENU, lambda e, k=key: self.read_panel(k), id=ident)
            accel.append((wx.ACCEL_ALT, ord(str(n)), ident))
        ident = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, lambda e: self.fight_menu(), id=ident)
        accel.append((wx.ACCEL_ALT, ord("8"), ident))
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
        self._item(game, tr("menu.disconnect"), lambda e: self.disconnect())
        self._item(game, tr("menu.resumerun"), lambda e: self.resume_run())
        self._item(game, tr("menu.autologin"), lambda e: self.open_autologin())
        self._item(game, tr("menu.server"), lambda e: self.choose_server())
        self._item(game, tr("menu.account"), lambda e: self.open_account())
        game.AppendSeparator()
        self._item(game, tr("menu.links"), lambda e: self.show_links())
        self._item(game, tr("menu.chat"), lambda e: self.open_chat())
        self._item(game, tr("menu.rooms"), lambda e: self.open_rooms())
        self._item(game, tr("menu.areas"), lambda e: self.open_areas())
        self._item(game, tr("menu.guide"), lambda e: self.open_guide())
        self._item(game, tr("menu.status"), lambda e: self.read_status())
        panels = wx.Menu()
        self._item(panels, tr("menu.panel.all"), lambda e: self.show_panels())
        for key, _fn in status_mod.PANELS:
            self._item(panels, tr("menu.panel." + key).split("\t")[0], lambda e, k=key: self.read_panel(k))
        self._item(panels, tr("menu.panel.fight").split("\t")[0], lambda e: self.fight_menu())
        game.AppendSubMenu(panels, tr("menu.panels"))
        self._item(game, tr("menu.inventory"), lambda e: self.open_items("inventory"))
        self._item(game, tr("menu.equipment"), lambda e: self.open_items("equipment"))
        self._item(game, tr("menu.roomlist"), lambda e: self.open_items("room"))
        self._item(game, tr("menu.wholist"), lambda e: self.open_items("who"))
        for kind in ("shop", "services", "training", "skills"):
            self._item(game, tr("menu.tl." + kind), lambda e, k=kind: self.open_items(k))
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
        it = opts.AppendCheckItem(wx.ID_ANY, tr("menu.listmenus"))
        it.Check(bool(self.prefs.get("list_menus", True)))
        self.Bind(wx.EVT_MENU, lambda e: self.prefs.__setitem__("list_menus", e.IsChecked()), it)
        it = opts.AppendCheckItem(wx.ID_ANY, tr("menu.tones"))
        it.Check(bool(self.prefs.get("exit_tones", True)))
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_tones(), it)
        self.tones_item = it
        room = wx.Menu()
        sounds = self.prefs.setdefault("room_sounds", {})
        for kind in ("player", "mob", "item", "target"):
            it = room.AppendCheckItem(wx.ID_ANY, tr("rs." + kind))
            it.Check(bool(sounds.get(kind, True)))
            self.Bind(wx.EVT_MENU, lambda e, k=kind: self.toggle_room_sound(k, e.IsChecked()), it)
        opts.AppendSubMenu(room, tr("menu.roomsounds"))
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
        self._item(tools, tr("menu.autobuff"), lambda e: self.open_autobuff())
        self._item(tools, tr("menu.script"), lambda e: self.open_script_editor())
        self._item(tools, tr("menu.clearoutput"), lambda e: self.clear_output())
        tools.AppendSeparator()
        self._item(tools, tr("menu.settings"), lambda e: self.open_settings())
        mb.Append(tools, tr("menu.tools"))

        hlp = wx.Menu()
        self._item(hlp, tr("menu.keys"), lambda e: self.show_text(tr("keys.title"), tr("keys.text")))
        self._item(hlp, tr("menu.helpsearch"), lambda e: self.open_help_search())
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

    def autologin_chars(self):
        al = self.prefs.get("autologin") or {}
        chars = list(al.get("chars") or [])
        if not chars and (al.get("name") or "").strip():
            chars = [al["name"].strip()]
        return [c for c in chars if creds.load(c)]

    def pick_login(self):
        """Choose the character to log in with for this connection, or None."""
        al = self.prefs.get("autologin") or {}
        chars = self.autologin_chars() if al.get("enabled") else []
        if len(chars) <= 1:
            return chars[0] if chars else None
        last = al.get("last")
        if last in chars:
            chars.remove(last)
            chars.insert(0, last)
        dlg = wx.SingleChoiceDialog(self, self.tr("al2.which"), self.tr("al2.title"), chars)
        name = chars[dlg.GetSelection()] if dlg.ShowModal() == wx.ID_OK else None
        dlg.Destroy()
        if name and name != last:
            al["last"] = name
            if not os.environ.get("DLCLIENT_QUIET"):
                prefs_mod.save(self.prefs)
        return name

    def connect(self):
        if self.conn.is_open:
            return
        self.login_name = self.pick_login()
        self.login_asked = True
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
            self.refresh_site_data()
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
        elif command == "list" and args and isinstance(args[0], dict):
            if self.capture is not None:
                self.capture["frame"] = args[0]
        elif command == "msp":
            self.parser.msp_enabled = bool(args and args[0])
            if not self.parser.msp_enabled:
                self.sound.stop_all()
        elif command == "prompt" and args and isinstance(args[0], dict):
            self.prompt.update(args[0])
            self.play_exit_tones()
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
        elif command == "editor_open":
            wx.CallAfter(self.open_editor, str(args[0]) if args else "")
        elif command == "autobuff_list" and args and isinstance(args[0], dict):
            if self.autobuff_dlg:
                self.autobuff_dlg.on_data(args[0])
        elif command == "script_saved" and args and isinstance(args[0], dict):
            self.on_script_saved(args[0])
        elif command == "account_chars" and args and isinstance(args[0], dict):
            self.on_account_chars(args[0])
        elif command == "notify" and args:
            self.on_notify(str(args[0]))
        elif command == "boss_phase" and args:
            self.on_boss_phase(str(args[0]))
        elif command == "alert" and args:
            self.notice(str(args[0]))

    def answer_lang_menu(self):
        self.lang_answered = True
        self.lang_menu_waiting = False
        self.conn.send_line(GAME_MENU_CHOICE.get(self.tr.lang, "1"))

    QUIT_LINES = ("Too bad, but all good things come to an end eventually.",
                  "Шкода, але все хороше колись закінчується.",
                  "Жаль, но все хорошее когда-нибудь заканчивается.")

    def disconnect(self):
        """Quit the character first, so it does not stay in the world link-dead.
        If the game refuses (a fight, for example), a second press cuts the line."""
        if not self.conn.in_world or getattr(self, "quit_sent", 0) > time.time() - 10:
            self.quit_sent = 0
            return self.conn.disconnect()
        self.quit_sent = time.time()
        self.send_command("quit", echo=False)
        self.say(self.tr("state.quitting"))

    def on_console(self, raw):
        text = self.telnet.process(raw)
        if text and any(line in text for line in self.QUIT_LINES):
            self.quit_sent = 0
            self.conn.ended()
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
        self.note_run_left(lines)
        for kind, name, opts in msp:
            self.sound.handle(kind, name, opts)
        if self.prompt_due and not complete and lines and self.prefs.get("hide_prompt", True):
            lines[-1].text, lines[-1].links = "", []
        self.prompt_due = False
        if self.capture is not None:
            paged = [l for l in lines if textlists.is_pager(l.text)]
            self.capture["lines"].extend(l for l in lines if not textlists.is_pager(l.text))
            if paged:
                if self.capture.get("timer"):
                    self.capture["timer"].Stop()
                self.capture["timer"] = wx.CallLater(3000, self.finish_capture)
                self.conn.send_line("")
                return
            if not complete:
                if self.capture["kind"] in ("__text__", "__path__") and self.capture["lines"]:
                    self.capture["lines"].pop()
                self.finish_capture()
            return
        starts = self.append_lines(lines, complete)
        if self.refresh_wait and not complete:
            self.refresh_wait -= 1
            if self.refresh_wait <= 0:
                self.refresh_wait = 0
                self._recapture()
        if self.room_wait is not None:
            self.room_lines.extend(lines)
            if not complete:
                self.finish_room()
        self.run_triggers(lines, starts)
        if self.walk_until and time.time() < self.walk_until:
            head = "'%s'" % self.walk_name
            for line in lines:
                if line.text.strip().startswith(head) and line.links:
                    self.walk_until = 0
                    self.send_command("|".join(l.command for l in line.links if l.command))
                    if self.walk_then:
                        self.send_command(self.walk_then)
                        self.walk_then = None
                    break
        if self.prefs.get("speech"):
            skip = [w.lower() for w in self.prefs.get("speech_skip") or []]
            spoken = "\n".join(l.text for l in lines if l.text.strip() and l.text.strip() != ">"
                               and not any(w in l.text.lower() for w in skip))
            self.speech.say(spoken)

    def clear_output(self):
        self.output.Clear()
        self.lines = [["", []]]
        self.say(self.tr("output.cleared"))

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
        elif self.typed_list(text):
            pass
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
        name = getattr(self, "login_name", None)
        if name is None and not getattr(self, "login_asked", False):
            chars = self.autologin_chars() if al.get("enabled") else []
            name = chars[0] if len(chars) == 1 else None
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
        al = self.prefs.setdefault("autologin", {"enabled": False, "chars": []})
        chars = list(al.get("chars") or ([al["name"]] if al.get("name") else []))
        dlg = dialogs.AutoLoginDialog(self, self.tr, bool(al.get("enabled")), chars,
                                      lambda n: bool(creds.load(n)))
        if dlg.ShowModal() == wx.ID_OK:
            for low in dlg.removed:
                creds.delete(low)
            for name, password in dlg.passwords.values():
                creds.save(name, password)
            al["chars"] = dlg.chars
            al.pop("name", None)
            saved = [n for n in dlg.chars if creds.load(n)]
            al["enabled"] = dlg.enabled.GetValue() and bool(saved)
            if not os.environ.get("DLCLIENT_QUIET"):
                prefs_mod.save(self.prefs)
            self.say(self.tr("al2.on", ", ".join(saved)) if al["enabled"] else self.tr("al2.off"))
        dlg.passwords.clear()
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
        if low in ("action", "триггер", "тригер"):
            return self.hash_action(rest)
        if low in ("help", "помощь", "допомога"):
            return self.notice(self.tr("hash.help"))
        if low in ("autobuff", "автобафф", "автобаф"):
            return self.open_autobuff()
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
        try:
            here = int(self.prompt.get("vnum"))
        except (TypeError, ValueError):
            here = None

        def load():
            try:
                amap = AreaMap(fetch_graph(area), lang)
                dist = amap.steps_from(here)
                rooms = sorted(((v, r["name"], dist.get(v)) for v, r in amap.rooms.items() if r["name"]),
                               key=lambda r: (r[1].lower(), r[0]))
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
            self.walk_then = None
            self.walk_until = time.time() + 5 if how == dlg.WALK else 0
            self.send_command("path %d" % vnum)
        dlg.Destroy()
        self.input.SetFocus()

    def open_areas(self):
        self.say(self.tr("areas.loading"))
        lang = self.tr.lang

        def load():
            try:
                areas = fetch_areas(lang)
            except Exception:
                areas = None
            wx.CallAfter(self._areas_loaded, areas)
        threading.Thread(target=load, daemon=True).start()

    def refresh_site_data(self):
        """Keep the guide's website data fresh; at most one download a day."""
        lang = self.tr.lang
        threading.Thread(target=lambda: sitedata.refresh(lang), daemon=True).start()

    def guide_key(self):
        return (getattr(self, "guide_name", None) or getattr(self, "login_name", None) or "").lower()

    def guide_context(self):
        return dict((self.prefs.get("guide") or {}).get(self.guide_key()) or {})

    def save_guide_context(self, ctx):
        key = self.guide_key()
        if key:
            store = dict(self.prefs.get("guide") or {})
            store[key] = dict(ctx)
            self.prefs["guide"] = store

    def guide_char(self, data):
        """account_chars reply: fill in the current character's level and class."""
        current = str(data.get("current") or "")
        char = next((c for c in data.get("chars") or [] if isinstance(c, dict)
                     and str(c.get("name", "")).lower() == current.lower()), None)
        if not char:
            return
        self.guide_name = current
        ctx = self.guide_context()
        if str(char.get("level") or "").isdigit():
            ctx["level"] = int(char["level"])
        cls = char.get("class")
        if isinstance(cls, dict):
            cls = cls.get("en") or ""
        if cls:
            ctx["class"] = str(cls)
        self.save_guide_context(ctx)
        if self.guide_keep:
            if not self.guide_keep.char:
                self.guide_keep.char = self.guide_key()
            self.guide_keep.set_context(ctx)

    def open_guide(self):
        if self.guide_dlg:
            return
        lang = self.tr.lang
        if self.conn.rpc("account_chars"):
            self.guide_asked = True
        keep = self.guide_keep
        if keep and keep.lang == lang and keep.char == self.guide_key():
            return self._guide_show(keep)
        if keep:
            keep.Destroy()
            self.guide_keep = None
        self.say(self.tr("guide.loading"))

        def load():
            sitedata.refresh(lang)
            site = sitedata.Site.load(lang)
            wx.CallAfter(self._guide_loaded, site)
        threading.Thread(target=load, daemon=True).start()

    def _guide_loaded(self, site):
        if not site.ready():
            return self.say(self.tr("guide.offline"))
        if self.guide_dlg or self.guide_keep:
            return
        dlg = GuideDialog(self, self.tr, site, self.guide_context(), self.save_guide_context)
        dlg.lang, dlg.char = self.tr.lang, self.guide_key()
        self.guide_keep = dlg
        self._guide_show(dlg, first=True)

    def _guide_show(self, dlg, first=False):
        """Show the guide; closing only hides it, so Ctrl+J reopens it as it was left."""
        self.guide_dlg = dlg
        try:
            if first:
                dlg.choice = None
                names = dlg.choice if dlg.ShowModal() == wx.ID_OK else None
            else:
                names = dlg.choice if dlg.show_again() == wx.ID_OK else None
        finally:
            self.guide_dlg = None
        self.input.SetFocus()
        if names:
            self.walk_to_zone(names)

    def walk_to_zone(self, names):
        """Walk to the area with one of these names (any language), as the area list does."""
        lang = self.tr.lang
        want = [n.strip().lower() for n in names if n and n.strip()]

        def load():
            try:
                areas = fetch_areas(lang)
            except Exception:
                areas = None
            wx.CallAfter(found, areas)

        def found(areas):
            if not areas:
                return self.say(self.tr("areas.offline"))
            area = match_area(areas, want)
            if area:
                return self.walk_area(area, AREA_WALK)
            self.say(self.tr("guide.nozone", names[0]))
        threading.Thread(target=load, daemon=True).start()

    def _areas_loaded(self, areas):
        if not areas:
            return self.say(self.tr("areas.offline"))
        dlg = dialogs.AreasDialog(self, self.tr, areas, self.prefs.get("areas_sort", "name"))
        choice = dlg.choice if dlg.ShowModal() == wx.ID_OK else None
        self.prefs["areas_sort"] = dlg.sort_key()
        dlg.Destroy()
        self.input.SetFocus()
        if not choice:
            return
        area, how = choice
        if how == dlg.HELP:
            return self.send_command("help " + (area["en"] or area["ru"]))
        self.walk_area(area, AREA_ROUTE if how == dlg.ROUTE else AREA_WALK)

    def walk_area(self, area, how):
        route = area["route"]
        if not route:
            return self.say(area.get("note") or self.tr("areas.noroute"))
        then = (" " + self.tr("areas.then", area["note"])) if area.get("note") else ""
        if how == AREA_ROUTE:
            self.input.ChangeValue("run " + route)
            self.input.SetInsertionPointEnd()
            return self.say(self.tr("areas.route", route) + then)
        if area_key(self.prompt.get("area")) != MIDGAARD:
            self.input.ChangeValue("run " + route)
            self.input.SetInsertionPointEnd()
            return self.say(self.tr("areas.typed", route) + then)
        if str(self.prompt.get("vnum")) == str(MARKET_SQUARE):
            if then:
                self.say(then.strip())
            return self.send_command("run " + route)
        self.say(self.tr("areas.walking", area["name"]) + then)
        lang = self.tr.lang

        def find_square():
            try:
                name = dict(fetch_rooms(MIDGAARD, lang)).get(MARKET_SQUARE)
            except Exception:
                name = None
            wx.CallAfter(self._walk_via_square, name, "run " + route)
        threading.Thread(target=find_square, daemon=True).start()

    def _walk_via_square(self, name, then):
        if not name:
            self.input.ChangeValue(then)
            self.input.SetInsertionPointEnd()
            return self.say(self.tr("areas.typed", then[4:]))
        self.walk_name = name
        self.walk_then = then
        self.walk_until = time.time() + 5
        self.send_command("path %d" % MARKET_SQUARE)

    def open_help_search(self):
        lang = self.tr.lang
        if self.help_search.ctx is None or lang not in self.help_search.loaded:
            self.say(self.tr("hs.loading"))

            def load():
                try:
                    self.help_search.prepare(lang)
                    ok = True
                except Exception:
                    ok = False
                wx.CallAfter(self._help_ready, ok)
            threading.Thread(target=load, daemon=True).start()
            return
        self._help_ready(True)

    def _help_ready(self, ok):
        if not ok:
            return self.say(self.tr("hs.offline"))
        dlg = dialogs.HelpSearchDialog(self, self.tr, self.help_search, self.tr.lang,
                                       lambda t, interrupt=True: self.say(t, interrupt))
        dlg.ShowModal()
        choice = dlg.choice
        dlg.Destroy()
        self.input.SetFocus()
        if choice is not None:
            self.send_command("help %s" % choice)

    def open_editor(self, text):
        dlg = dialogs.EditorDialog(self, self.tr, text)
        if dlg.ShowModal() == wx.ID_OK:
            if self.conn.rpc("editor_save", dlg.value()):
                self.say(self.tr("ed.saved"))
            else:
                self.notice(self.tr("state.closed"))
        dlg.Destroy()
        self.input.SetFocus()

    def open_autobuff(self):
        dlg = dialogs.AutobuffDialog(self, self.tr, self.conn.rpc, lambda t: self.say(t))
        self.autobuff_dlg = dlg
        dlg.ShowModal()
        self.autobuff_dlg = None
        dlg.Destroy()
        self.input.SetFocus()

    def open_script_editor(self):
        dlg = dialogs.ScriptEditDialog(self, self.tr, self.script.text or self.script.stock_text(),
                                       self.script.source)
        while dlg.ShowModal() == wx.ID_OK:
            text = dlg.value()
            raw = text.encode("utf-8")
            if len(raw) > 65536:
                wx.MessageBox(self.tr("se.toobig"), self.tr("se.title"), wx.OK | wx.ICON_WARNING, dlg)
                continue
            stock = text.strip() == (self.script.stock_text() or "").strip()
            if not stock and not self.script.load(text, "account"):
                continue
            if stock:
                self.script.load_stock()
            b64 = "" if stock else base64.b64encode(raw).decode("ascii")
            if not self.conn.rpc("script_put", b64):
                self.notice(self.tr("state.closed"))
            break
        dlg.Destroy()
        self.input.SetFocus()

    def on_script_saved(self, data):
        if data.get("ok"):
            return self.notice(self.tr("se.saved"))
        reason = str(data.get("reason") or "io")
        key = "se.reason." + reason
        text = self.tr(key)
        self.notice(self.tr("se.fail", reason if text == key else text))

    def open_account(self):
        if not self.conn.rpc("account_chars"):
            return self.notice(self.tr("state.closed"))
        self.say(self.tr("acc.loading"))
        if self.account_wait:
            self.account_wait.Stop()
        self.account_wait = wx.CallLater(2500, lambda: self.say(self.tr("acc.noreply")))

    def on_account_chars(self, data):
        if self.guide_asked:
            self.guide_asked = False
            self.guide_char(data)
        if not self.account_wait:
            return
        self.account_wait.Stop()
        self.account_wait = None
        dlg = dialogs.AccountDialog(self, self.tr, data)
        choice = dlg.choice if dlg.ShowModal() == wx.ID_OK else None
        dlg.Destroy()
        self.input.SetFocus()
        if not choice:
            return
        char, how = choice
        name = str(char.get("name"))
        if not re.fullmatch(r"[A-Za-z]{1,20}", name):
            return
        if how == dialogs.AccountDialog.SWITCH:
            self.send_command("account switch " + name)
        else:
            hidden = (char.get("profile") or {}).get("hidden")
            self.send_command("account profile %s %s" % ("show" if hidden else "hide", name))

    TONE_ORDER = (("n", "north"), ("e", "east"), ("s", "south"), ("w", "west"), ("u", "up"), ("d", "down"))

    ROOM_SOUND_ORDER = ("target", "player", "mob", "item")

    def play_exit_tones(self):
        room = self.prompt.get("vnum")
        if room is None or room == self.tone_room:
            return
        first = self.tone_room is None
        self.tone_room = room
        if first:
            return
        dirs = []
        exits = self.prompt.get("exits")
        if self.prefs.get("exit_tones", True) and isinstance(exits, dict):
            visible = str(exits.get("e") or "").lower()
            dirs = [name for letter, name in self.TONE_ORDER if letter in visible]
        for i, name in enumerate(dirs):
            if i == 0:
                self.sound.exit_tone(name, i)
            else:
                wx.CallLater(130 * i, self.sound.exit_tone, name, i)
        self.room_lines = []
        self.room_wait = (time.time() + (130 * len(dirs) + (120 if dirs else 0)) / 1000.0, len(dirs))
        if self.room_timer:
            self.room_timer.Stop()
        self.room_timer = wx.CallLater(800, self.finish_room)

    def finish_room(self):
        if self.room_wait is None:
            return
        due, first = self.room_wait
        self.room_wait = None
        if self.room_timer:
            self.room_timer.Stop()
            self.room_timer = None
        seen, self.room_lines = self.room_lines, []
        wanted = self.prefs.get("room_sounds") or {}
        present = classify(seen)
        kinds = [k for k in self.ROOM_SOUND_ORDER if k in present and wanted.get(k, True)]
        for j, kind in enumerate(kinds):
            self.sound.exit_tone(kind, j, "room")

    def toggle_room_sound(self, kind, on):
        self.prefs.setdefault("room_sounds", {})[kind] = on
        self.say(self.tr("rs.state", self.tr("rs." + kind).replace("&", ""),
                         self.tr("rs.on" if on else "rs.off")))

    def toggle_tones(self):
        self.prefs["exit_tones"] = not self.prefs.get("exit_tones", True)
        self.tones_item.Check(self.prefs["exit_tones"])
        self.say(self.tr("tones.on" if self.prefs["exit_tones"] else "tones.off"))

    def choose_server(self):
        from .connection import URL
        dlg = wx.TextEntryDialog(self, self.tr("server.label", URL), self.tr("server.title"),
                                 self.prefs.get("server") or URL)
        if dlg.ShowModal() == wx.ID_OK:
            value = dlg.GetValue().strip()
            if value and not value.startswith(("ws://", "wss://")):
                value = "ws://" + value
            self.prefs["server"] = "" if value in ("", URL) else value
            self.conn.url = self.prefs["server"] or URL
            self.say(self.tr("server.set", self.conn.url))
        dlg.Destroy()
        self.input.SetFocus()

    TYPED = {}
    for _kind, _words in (
            ("inventory", "i inv inventory инвентарь вещи інвентар речі"),
            ("equipment", "eq equip equipment снаряжение экипировка одежда спорядження екіпірування одяг"),
            ("who", "who кто хто"),
            ("shop", "list список ассортимент асортимент"),
            ("services", "service услуга послуга"),
            ("training", "train gain тренировать тренировки тренувати тренування"),
            ("skills", "prac practice практиковать практикувати"),
            ("skilltable", "skills умения вміння"),
            ("questshop", "quest|list квест|список"),
            ("questrequest", "quest|request квест|попросить квест|попросити"),
            ("zonequests", "quest квест"),
            ("areas", "areas зоны зони"),
            ("notes", "note|list news|list change|list idea|list story|list qnote|list"),
            ("helpmatches", "help справка довідка"),
            ("glist", "glist"),
            ("socials", "socials социалы соціали"),
            ("commands", "commands команды команди"),
            ("linked", "vault хранилище сховище where где де craft")):
        for _w in _words.split():
            TYPED[_w.replace("|", " ")] = _kind

    TYPED_WITH_ARGS = {"skilltable", "shop", "who", "areas", "helpmatches", "glist", "equipment"}

    def typed_list(self, text):
        if not self.prefs.get("list_menus", True) or not self.conn.in_world or self.capture or self.items_dlg:
            return False
        words = text.lower().split()
        kind = self.TYPED.get(" ".join(words))
        command = " ".join(text.split())
        if len(words) > 2 and words[0] in ("l", "lo", "loo", "look") and words[1] == "in":
            target = " ".join(text.split()[2:])
            self.open_items("container", command, target, container=target)
            return True
        if not kind and len(words) > 1:
            first = self.TYPED.get(words[0])
            if first in self.TYPED_WITH_ARGS:
                kind = first
            elif first == "linked" and words[0] in ("vault", "хранилище", "сховище", "where", "где", "де"):
                kind = first
            elif words[0] == "craft" and words[1] in ("filter", "list"):
                kind = "linked"
        if not kind:
            return False
        self.open_items(kind, command)
        return True

    LISTS = {"inventory": ("inventory", "items.inventory"), "equipment": ("equipment", "items.equipment"),
             "room": ("look", "items.room"), "who": ("who", "items.who")}

    def open_items(self, kind, command=None, title=None, container=None):
        if not self.conn.in_world:
            return self.say(self.tr("rooms.nowhere"))
        if kind in self.LISTS:
            default, key = self.LISTS[kind]
            command = command or default
            title = self.tr(key)
        elif kind in textlists.PARSERS:
            default, _parser, key, _keys = textlists.PARSERS[kind]
            command = command or default
            title = self.tr(key)
        if self.capture and self.capture.get("timer"):
            self.capture["timer"].Stop()
        self.capture = {"kind": kind, "title": title, "container": container, "lines": [], "command": command,
                        "timer": wx.CallLater(3000, self.finish_capture)}
        self.send_command(command, echo=False)

    INFO_VERBS = {"help", "look", "l", "examine", "exa", "read", "consider", "con", "whois", "compare",
                  "properties", "lore", "score", "affects", "effects", "worth"}

    @classmethod
    def is_info(cls, command):
        words = command.lower().split()
        if not words or "in" in words[1:2]:
            return False
        if words[0] in cls.INFO_VERBS:
            return True
        if words[0] == "quest" and len(words) == 2 and (words[1].isdigit() or words[1] == "info"):
            return True
        return len(words) > 1 and words[1] in ("read", "look", "info", "show")

    RUN_LEFT = ("You still have left to run:", "Тобі залишалося бігти:", "Тебе оставалось бежать:")

    def note_run_left(self, lines):
        """Remember the rest of a run the game stopped, so it can be resumed."""
        for line in lines:
            if line.text.strip().startswith(self.RUN_LEFT):
                cmd = next((l.command for l in line.links if (l.command or "").startswith("run ")), None)
                if not cmd:
                    rest = line.text.split(":", 1)[1].strip()
                    cmd = "run " + rest if rest else None
                if cmd:
                    self.run_left = cmd
                    wx.CallAfter(self.say, self.tr("run.stopped"))

    def resume_run(self):
        cmd = getattr(self, "run_left", None)
        if not cmd:
            return self.say(self.tr("run.none"))
        self.run_left = None
        self.send_command(cmd)

    def walk_path(self, command):
        """Ask the game for the route to a room and run it, closing the list."""
        if self.capture and self.capture.get("timer"):
            self.capture["timer"].Stop()
        self.capture = {"kind": "__path__", "title": command, "lines": [], "command": command,
                        "timer": wx.CallLater(3000, self.finish_capture)}
        self.send_command(command, echo=False)

    def show_help(self, command, title=None):
        if self.capture and self.capture.get("timer"):
            self.capture["timer"].Stop()
        title = title or (command.split(" ", 1) + [command])[1].strip()
        self.capture = {"kind": "__text__", "title": title, "lines": [],
                        "command": command, "timer": wx.CallLater(3000, self.finish_capture)}
        self.send_command(command, echo=False)

    REFRESH_VERBS = {"drop", "sacrifice", "wear", "remove", "get", "kill"}

    def finish_capture(self):
        cap, self.capture = self.capture, None
        if not cap:
            return
        if cap.get("timer"):
            cap["timer"].Stop()
        if cap["kind"] == "__path__":
            route = next((link.command for line in cap["lines"] for link in line.links
                          if (link.command or "").startswith("run ")), None)
            if route:
                if self.items_dlg:
                    self.items_dlg.EndModal(wx.ID_OK)
                return wx.CallAfter(self.send_command, route)
            cap["kind"] = "__text__"
        if cap["kind"] == "__text__":
            text = "\n".join(line.text.rstrip() for line in cap["lines"]).strip()
            dlg = TextDialog(self.items_dlg or self, cap["title"], text or self.tr("items.none"), self.tr("ok"))
            dlg.ShowModal()
            dlg.Destroy()
            return
        rows = []
        keys_text = None
        compare = self.tr("items.compare")
        frame = cap.get("frame")
        if frame is not None:
            rows = framelists.rows_from_frame(frame, self.tr, cap["kind"])
            if cap["kind"] in textlists.PARSERS:
                keys_text = self.tr(textlists.PARSERS[cap["kind"]][3])
        elif cap["kind"] in textlists.PARSERS:
            _cmd, parser, _title, keys_key = textlists.PARSERS[cap["kind"]]
            rows = parser(cap["lines"], self.tr, cap.get("command") or "") if parser else []
            keys_text = self.tr(keys_key)
        for line in (cap["lines"] if cap["kind"] not in textlists.PARSERS and frame is None else []):
            if cap["kind"] == "equipment" and not any(l.menu for l in line.links) and line.text.rstrip().endswith("nothing."):
                rows.append({"label": " ".join(line.text.split()), "kind": "custom", "menu": [], "keys": {},
                             "refresh": set()})
                continue
            for link in line.links:
                if not link.menu:
                    continue
                ident = getattr(link, "ident", "") or ""
                kind = kind_of(link)
                entries = list(link.menu)
                if kind == "item" and cap["kind"] == "inventory" and ident.isdigit():
                    entries = entries + [None, (compare, "compare " + ident)]
                rows.append({"label": " ".join(line.text.split()), "menu": entries, "ident": ident,
                             "kind": kind, "name": link.label, "container": cap.get("container")})
                if cap["kind"] != "who":
                    break
        if not rows and not self.items_dlg:
            shown = [l for l in cap["lines"] if l.text.strip()]
            if shown:
                if self.lines[-1][0]:
                    self.append_lines([], True)
                self.append_lines(shown, True)
                if self.prefs.get("speech"):
                    self.speech.say("\n".join(l.text for l in shown))
            else:
                self.say(self.tr("items.none"))
            return
        self.items_view = cap
        if self.items_dlg:
            return self.items_dlg.set_rows(cap["title"], rows, keys_text)
        dlg = dialogs.ItemsDialog(self, self.tr, cap["title"], rows, self.item_action, keys_text)
        self.items_dlg = dlg
        dlg.ShowModal()
        self.items_dlg = None
        dlg.Destroy()
        self.input.SetFocus()

    def item_action(self, choice):
        how, what, row = choice
        if row.get("kind") == "custom":
            cmds = what if how == "commands" else [what]
            if row.get("open") and cmds == [row["open"][1]]:
                return self.open_items(row["open"][0], row["open"][1])
            if cmds and cmds[0].startswith(("__target__ ", "__input__ ")):
                if self.items_dlg:
                    self.items_dlg.EndModal(wx.ID_OK)
                self.input.ChangeValue(cmds[0].split(" ", 1)[1] + " ")
                self.input.SetInsertionPointEnd()
                hint = "tl.typetarget" if cmds[0].startswith("__target__ ") else "tl.typemessage"
                return wx.CallAfter(self.say, self.tr(hint))
            if len(cmds) == 1 and cmds[0].lower().startswith("path ") and self.items_dlg:
                return self.walk_path(cmds[0])
            if len(cmds) == 1 and self.is_info(cmds[0]) and self.items_dlg:
                return self.show_help(cmds[0], row.get("label"))
            if row.get("close") and self.items_dlg:
                self.items_dlg.EndModal(wx.ID_OK)
            for cmd in cmds:
                self.send_command(cmd)
            if any(cmd in row.get("refresh", set()) for cmd in cmds):
                self.refresh_items(len(cmds))
            return
        if how == "command":
            if self.is_info(what) and self.items_dlg:
                return self.show_help(what, row.get("label"))
            self.send_command(what)
            return self.refresh_items(1)
        if "tell" in what:
            if self.items_dlg:
                self.items_dlg.EndModal(wx.ID_OK)
            target = row["name"]
            self.input.ChangeValue("tell %s " % target)
            self.input.SetInsertionPointEnd()
            return wx.CallAfter(self.say, self.tr("items.tell", target))
        if len(what) == 1 and what[0] in self.INFO_VERBS and self.items_dlg and row.get("ident"):
            target = row["ident"] if row["kind"] != "player" else row["name"]
            return self.show_help("%s %s" % (what[0], target), row.get("label"))
        sent = self.item_verbs(what, row)
        if set(what) & self.REFRESH_VERBS:
            self.refresh_items(sent)

    def refresh_items(self, commands):
        if self.items_view and self.items_dlg:
            self.refresh_wait = max(1, commands or 1)

    def _recapture(self):
        view = self.items_view
        if not view or not self.items_dlg:
            return
        command = view.get("command") or {"inventory": "inventory", "equipment": "equipment", "room": "look",
                                          "who": "who"}.get(view["kind"])
        if view["kind"] in textlists.PARSERS:
            command = view.get("command") or textlists.PARSERS[view["kind"]][0]
        if view["kind"] == "container":
            command = "look in " + view["container"]
        if not command:
            return
        self.capture = {"kind": view["kind"], "title": view["title"], "container": view.get("container"),
                        "lines": [], "command": view.get("command"), "timer": wx.CallLater(3000, self.finish_capture)}
        self.send_command(command, echo=False)

    def item_verbs(self, verbs, row):
        ident = row["ident"]
        target = ident if row["kind"] != "player" else row["name"]
        sent = 0
        for verb in verbs:
            if verb == "open":
                self.open_items("container", "look in " + ident, row["label"], container=ident)
                return 0
            if verb == "get" and row.get("container"):
                self.send_command("get %s %s" % (ident, row["container"]))
            else:
                self.send_command("%s %s" % (verb, target))
            sent += 1
        return sent

    def read_panel(self, key):
        fn = dict(status_mod.PANELS)[key]
        self.say(fn(self.prompt, self.tr))

    def show_panels(self):
        self.show_text(self.tr("panels.title"), status_mod.everything(self.prompt, self.tr))

    def fight_menu(self):
        cmds = status_mod.fight_commands(self.prompt)
        if not cmds:
            return self.say(self.tr("fight.none"))
        menu = wx.Menu()
        for cmd in cmds:
            it = menu.Append(wx.ID_ANY, cmd)
            self.Bind(wx.EVT_MENU, lambda e, c=cmd: self.send_command(c), it)
        self.PopupMenu(menu)
        menu.Destroy()

    def on_notify(self, text):
        text = status_mod.clean(text)
        self.sound.play("ui/notify", {"T": "ui"})
        if self.IsActive():
            return
        self.RequestUserAttention()
        try:
            import wx.adv
            note = wx.adv.NotificationMessage(self.tr("notify.title"), text, self)
            note.Show()
        except Exception:
            pass

    def on_boss_phase(self, kind):
        if kind not in ("control", "panic"):
            return
        self.sound.play("alert/raid", {"T": "alert"})
        self.notice(self.tr("boss." + kind))

    def hash_action(self, rest):
        if not self.triggers.known:
            return self.notice(self.tr("hash.wait"))
        m = re.fullmatch(r"\{(.+?)\}\s*\{(.*)\}", rest.strip())
        mine = list(self.triggers.lists.get("char") or [])
        if m:
            pattern, action = m.group(1).strip(), m.group(2).strip()
            if action.lower() in ("delete", "удалить", "видалити"):
                kept = [t for t in mine if t.get("pattern") != pattern]
                self.triggers.set_list("char", kept)
                return self.notice(self.tr("hash.action.deleted", len(mine) - len(kept)))
            if not pattern or not action:
                return self.notice(self.tr("hash.action.usage"))
            if len(mine) >= self.triggers.max_items:
                return self.notice(self.tr("list.full"))
            mine.append({"id": new_id(), "pattern": pattern, "cmd": action})
            self.triggers.set_list("char", mine)
            return self.notice(self.tr("hash.action.set", pattern, action))
        words = rest.split()
        if words and words[-1].lower() in ("delete", "удалить", "видалити"):
            needle = " ".join(words[:-1]).lower()
            kept = [t for t in mine if needle not in (t.get("pattern") or "").lower()]
            self.triggers.set_list("char", kept)
            return self.notice(self.tr("hash.action.deleted", len(mine) - len(kept)))
        needle = rest.strip().lower()
        rows = [t for t in mine if needle in (t.get("pattern") or "").lower()]
        if not rows:
            return self.notice(self.tr("hash.action.none", rest.strip()) if needle else self.tr("hash.action.empty"))
        return self.notice(self.tr("hash.action.list") + "\n" + "\n".join(
            "    {%s} {%s}" % (t.get("pattern", ""), t.get("cmd", "")) for t in rows))

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
        dlg = dialogs.UpdateDialog(self, self.tr, info["tag"].lstrip("v"), VERSION, info["notes"].strip())
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
