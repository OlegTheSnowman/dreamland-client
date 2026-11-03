"""The main window: game output above, command field below."""

import os
import threading
import time
import webbrowser

import wx

from . import prefs as prefs_mod
from .connection import Connection, PROTO_VERSION
from .i18n import GAME_MENU_CHOICE, LANGS, Tr
from . import dialogs
from .markup import Line, OutputParser
from .scripting import Aliases, Macros, Triggers, VAR_NAME, canonical_key, expand_vars
from .sound import SoundPlayer, fetch_from_url, fetch_live_library
from .speech import Speech
from .telnet import Telnet

MAX_LINES = 20000
TRIM_LINES = 4000
HISTORY_MAX = 200
LINK_LIST_LINES = 300


class MainFrame(wx.Frame):
    def __init__(self, app_dir):
        self.app_dir = app_dir
        self.prefs = prefs_mod.load()
        if os.environ.get("DLCLIENT_QUIET"):
            # Test launches: no sound, no speech, nothing saved.
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
        self.telnet = Telnet()
        self.conn = Connection(self._frame_from_thread, self._state_from_thread)
        later = lambda secs, fn: wx.CallLater(int(secs * 1000), fn)
        self.triggers = Triggers(self.conn.rpc, later)
        self.macros = Macros(self.conn.rpc, later)
        self.aliases = Aliases(self.conn.rpc, self.conn.send_line, later)
        self.vars = self.prefs.setdefault("vars", {})
        self.settings_dlg = None

        self.lines = [["", []]]    # [text, links] per output line; last one is open
        self.history = list(self.prefs.get("history", []))[-HISTORY_MAX:]
        self.hist_pos = None
        self.prompt = {}
        self.lang_answered = False
        self.lang_menu_waiting = False
        self.nanny_password = False   # the login is asking for a password

        self._build()
        self._build_menu()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.input.SetFocus()
        wx.CallAfter(self.connect)

    # ------------------------------------------------------------------ layout
    def _build(self):
        # Exactly two controls: the output and the command field. Tab and
        # Shift+Tab move between them. Their names come through accessibility,
        # not through visible labels, so nothing else is in the window.
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

    def _build_menu(self):
        tr = self.tr
        mb = wx.MenuBar()

        game = wx.Menu()
        self._item(game, tr("menu.connect"), lambda e: self.connect())
        self._item(game, tr("menu.disconnect"), lambda e: self.conn.disconnect())
        game.AppendSeparator()
        self._item(game, tr("menu.links"), lambda e: self.show_links())
        self._item(game, tr("menu.status"), lambda e: self.read_status())
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
        self._item(opts, tr("menu.volume_up"), lambda e: self.change_volume(10))
        self._item(opts, tr("menu.volume_down"), lambda e: self.change_volume(-10))
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
        mb.Append(hlp, tr("menu.help"))

        self.SetMenuBar(mb)

    def _item(self, menu, label, handler):
        it = menu.Append(wx.ID_ANY, label)
        self.Bind(wx.EVT_MENU, handler, it)
        return it

    def _update_sounds(self, live, then=None):
        try:
            if fetch_live_library(live, os.path.join(self.app_dir, "sounds")):
                wx.CallAfter(self.sound.reload)
                if then:
                    wx.CallAfter(then)
        except Exception:
            pass  # offline or the site changed: the bundled sounds still play

    def _sound_missing(self, kind, name, opts):
        """A sound the library does not have: fetch it, then play it if it arrives."""
        url = (opts or {}).get("U")
        if url:
            def get():
                try:
                    full = url if url.lower().endswith((".mp3", ".ogg", ".wav")) else url.rstrip("/") + "/" + name
                    got = fetch_from_url(full, self.sound_live)
                except Exception:
                    got = None
                if got:
                    wx.CallAfter(self.sound.reload)
                    wx.CallAfter(self.sound.handle, kind, got, {k: v for k, v in opts.items() if k != "U"})
            threading.Thread(target=get, daemon=True).start()
            return
        # The web client may have gained the sound since we last looked.
        if time.time() - self.sound_refreshed < 300:
            return
        self.sound_refreshed = time.time()
        replay = lambda: self.sound.resolve(name) and self.sound.handle(kind, name, opts)
        threading.Thread(target=self._update_sounds, args=(self.sound_live, replay), daemon=True).start()

    # ------------------------------------------------------------- connection
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
            self.nanny_password = step in ("password", "password_confirm")
            self.set_password_mode(self.nanny_password or self.telnet.echo_off)
        elif command == "version":
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
            self.update_status()
            if self.nanny_password:
                self.nanny_password = False
                self.set_password_mode(self.telnet.echo_off)
            self.triggers.ask()
            self.macros.ask()
            self.aliases.ask()
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
        starts = self.append_lines(lines, complete)
        self.run_triggers(lines, starts)
        if self.prefs.get("speech"):
            spoken = "\n".join(l.text for l in lines if l.text.strip() and l.text.strip() != ">")
            self.speech.say(spoken)

    # ----------------------------------------------------------------- output
    def append_lines(self, lines, complete):
        if not lines and not complete:
            return []
        out = self.output
        # While the player reads the output, the caret and selection stay
        # exactly where they are; new text never drags them to the end.
        reading = wx.Window.FindFocus() is out
        sel = out.GetSelection()
        base = out.GetLastPosition()
        starts = []
        chunks = []
        for i, line in enumerate(lines):
            if i > 0:
                self.lines.append(["", []])
                chunks.append("\n")
            cur = self.lines[-1]
            shift = len(cur[0])
            starts.append(base + sum(len(c) for c in chunks))
            for l in line.links:
                l.start += shift
                l.end += shift
            cur[0] += line.text
            cur[1].extend(line.links)
            chunks.append(line.text)
        if complete:
            self.lines.append(["", []])
            chunks.append("\n")
        out.AppendText("".join(chunks))
        if len(self.lines) > MAX_LINES:
            cut = sum(len(t) + 1 for t, _ in self.lines[:TRIM_LINES])
            del self.lines[:TRIM_LINES]
            out.Remove(0, cut)
            sel = (max(0, sel[0] - cut), max(0, sel[1] - cut))
            starts = [max(0, x - cut) for x in starts]
        if reading:
            out.SetSelection(*sel)
        return starts

    def notice(self, text, speak=True):
        """A line from the client itself, shown and spoken."""
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

    def current_line(self):
        pos = self.output.GetInsertionPoint()
        before = self.output.GetRange(0, pos)
        row = before.count("\n")
        col = pos - (before.rfind("\n") + 1)
        return min(row, len(self.lines) - 1), col

    # ----------------------------------------------------------------- input
    def on_enter(self, event):
        text = self.input.GetValue()
        self.input.ChangeValue("")
        if self.password_mode:
            # Never echoed, spoken, stored or replayed.
            self.conn.send_line(text)
            return
        if text.startswith("#"):
            self.echo(text)
            self.hash_command(text)
        else:
            self.send_command(text, expand=True)
        if text.strip() and (not self.history or self.history[-1] != text):
            self.history.append(text)
            del self.history[:-HISTORY_MAX]
        self.hist_pos = None

    def send_command(self, text, echo_text=None, expand=False):
        self.echo(echo_text if echo_text is not None else text)
        if expand:
            text = self.aliases.expand(text)
        if not self.conn.send_line(text):
            self.notice(self.tr("state.closed"))

    def on_input_key(self, event):
        if self.password_mode:
            # No macros, history or drafts while a password is being typed.
            return event.Skip()
        if self.run_macro(event):
            return
        key = event.GetKeyCode()
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
            self.keep_draft()
            self.input.ChangeValue("")
            self.hist_pos = None
            return
        event.Skip()

    def keep_draft(self):
        """Put typed but unsent text into the history, so Up finds it again."""
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
            # The draft is now the newest entry; Up goes on to the one before it.
            self.hist_pos = len(self.history) - 1
        else:
            self.hist_pos = min(self.hist_pos, len(self.history) - 1)

    def set_password_mode(self, on):
        """Mask the command field itself, so the window keeps only two controls."""
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
        # Typing in the output goes to the command field.
        code = event.GetUnicodeKey()
        if code >= 32 and not event.ControlDown() and not event.AltDown():
            self.input.SetFocus()
            self.input.WriteText(chr(code))
            return
        event.Skip()

    # ------------------------------------------------- triggers, macros, hash
    def reset_lists(self):
        # A new socket or a login change: the lists belong to the old character.
        self.triggers.reset()
        self.macros.reset()
        self.aliases.reset()

    def run_triggers(self, lines, starts):
        texts = [l.text for l in lines]
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
        if not self.macros.known:
            return False
        name = dialogs.key_from_event(event)
        if not name:
            return False
        cmd = self.macros.command_for(name)
        if cmd is None:
            fallback = dialogs.key_fallback_from_event(event)
            if fallback:
                cmd = self.macros.command_for(fallback)
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

    # ----------------------------------------------------------------- links
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

    # ----------------------------------------------------------------- status
    def update_status(self):
        pass  # no status bar: Ctrl+S reads the status

    def status_text(self):
        p = self.prompt
        if "hit" not in p:
            return self.tr("status.none")
        s = self.tr("status.line", p.get("hit"), p.get("max_hit"), p.get("mana"),
                    p.get("max_mana"), p.get("move"), p.get("max_move"))
        if p.get("fight"):
            s += " " + self.tr("status.fighting")
        return s

    def read_status(self):
        self.say(self.status_text(), interrupt=True)

    # ---------------------------------------------------------------- options
    def say(self, text, interrupt=True):
        # Answers to the player's own keys are spoken even with speech of
        # incoming text off: otherwise the key would seem to do nothing.
        self.speech.say(text, interrupt=interrupt)

    def toggle_speech(self):
        self.prefs["speech"] = not self.prefs.get("speech")
        self.speech_item.Check(self.prefs["speech"])
        self.say(self.tr("speech.on" if self.prefs["speech"] else "speech.off"))

    def toggle_echo(self):
        self.prefs["echo"] = not self.prefs.get("echo", True)
        self.echo_item.Check(self.prefs["echo"])
        self.say(self.tr("echo.on" if self.prefs["echo"] else "echo.off"))

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

    def on_close(self, event):
        self.prefs["history"] = self.history[-HISTORY_MAX:]
        if not os.environ.get("DLCLIENT_QUIET"):
            try:
                prefs_mod.save(self.prefs)
            except OSError:
                pass
        self.conn.disconnect()
        self.sound.stop_all()
        event.Skip()


class NamedAccessible(wx.Accessible):
    """Gives a control its spoken name without a visible label next to it.

    Only the name is answered here; role, value and the rest still come from
    the native control.
    """

    def __init__(self, ctrl, name):
        super().__init__(ctrl)
        self.name = name
        ctrl.SetAccessible(self)

    def GetName(self, childId):
        if childId == 0:
            return (wx.ACC_OK, self.name)
        return (wx.ACC_NOT_IMPLEMENTED, "")


EM_SETPASSWORDCHAR = 0xCC


def set_password_char(ctrl, on):
    """Mask or unmask a single-line text field in place (Windows edit control)."""
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
