"""The main window: game output above, command field below."""

import json
import os
import webbrowser

import wx

from . import prefs as prefs_mod
from .connection import Connection, PROTO_VERSION
from .i18n import GAME_MENU_CHOICE, LANGS, Tr
from .markup import Link, OutputParser
from .sound import SoundPlayer
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
        self.sound = SoundPlayer(os.path.join(app_dir, "sounds"), self.prefs["sound"])
        self.parser = OutputParser()
        self.telnet = Telnet()
        self.conn = Connection(self._frame_from_thread, self._state_from_thread)

        self.lines = [["", []]]    # [text, links] per output line; last one is open
        self.history = list(self.prefs.get("history", []))[-HISTORY_MAX:]
        self.hist_pos = None
        self.prompt = {}
        self.lang_answered = False
        self.lang_menu_waiting = False

        self._build()
        self._build_menu()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.input.SetFocus()
        wx.CallAfter(self.connect)

    # ------------------------------------------------------------------ layout
    def _build(self):
        panel = wx.Panel(self)
        self.panel = panel
        self.output_label = wx.StaticText(panel, label=self.tr("output.name"))
        self.output = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_NOHIDESEL)
        self.output.SetName(self.tr("output.name"))
        self.input_label = wx.StaticText(panel, label=self.tr("input.name"))
        self.input = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.input.SetName(self.tr("input.name"))
        self.password = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER | wx.TE_PASSWORD)
        self.password.SetName(self.tr("password.name"))
        self.password.Hide()

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(self.output_label, 0, wx.LEFT | wx.TOP, 4)
        s.Add(self.output, 1, wx.EXPAND | wx.ALL, 4)
        s.Add(self.input_label, 0, wx.LEFT, 4)
        s.Add(self.input, 0, wx.EXPAND | wx.ALL, 4)
        s.Add(self.password, 0, wx.EXPAND | wx.ALL, 4)
        panel.SetSizer(s)

        self.CreateStatusBar()

        self.input.Bind(wx.EVT_TEXT_ENTER, self.on_enter)
        self.password.Bind(wx.EVT_TEXT_ENTER, self.on_enter)
        self.input.Bind(wx.EVT_KEY_DOWN, self.on_input_key)
        self.output.Bind(wx.EVT_KEY_DOWN, self.on_output_key)
        self.output.Bind(wx.EVT_CHAR, self.on_output_char)
        self.output.Bind(wx.EVT_CONTEXT_MENU, lambda e: self.line_menu(always_menu=True))

        self.id_f6 = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, self.on_f6, id=self.id_f6)
        self.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_NORMAL, wx.WXK_F6, self.id_f6)]))

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
        self._item(opts, tr("menu.volume_up"), lambda e: self.change_volume(10))
        self._item(opts, tr("menu.volume_down"), lambda e: self.change_volume(-10))
        mb.Append(opts, tr("menu.options"))

        hlp = wx.Menu()
        self._item(hlp, tr("menu.keys"), lambda e: self.show_text(tr("keys.title"), tr("keys.text")))
        self._item(hlp, tr("menu.credits"), lambda e: self.show_credits())
        mb.Append(hlp, tr("menu.help"))

        self.SetMenuBar(mb)

    def _item(self, menu, label, handler):
        it = menu.Append(wx.ID_ANY, label)
        self.Bind(wx.EVT_MENU, handler, it)
        return it

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
        elif command == "version":
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
        self.set_password_mode(self.telnet.echo_off)
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
        self.append_lines(lines, complete)
        if self.prefs.get("speech"):
            spoken = "\n".join(l.text for l in lines if l.text.strip() and l.text.strip() != ">")
            self.speech.say(spoken)

    # ----------------------------------------------------------------- output
    def append_lines(self, lines, complete):
        if not lines and not complete:
            return
        out = self.output
        pos = out.GetInsertionPoint()
        at_end = pos >= out.GetLastPosition()
        chunks = []
        for i, line in enumerate(lines):
            if i > 0:
                self.lines.append(["", []])
                chunks.append("\n")
            cur = self.lines[-1]
            shift = len(cur[0])
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
            pos = max(0, pos - cut)
        if not at_end:
            out.SetInsertionPoint(pos)

    def notice(self, text, speak=True):
        """A line from the client itself, shown and spoken."""
        if self.lines[-1][0]:
            self.append_lines([], True)
        from .markup import Line
        self.append_lines([Line(text, [])], True)
        self.SetStatusText(text)
        if speak and self.prefs.get("speech"):
            self.speech.say(text)

    def echo(self, text):
        from .markup import Line
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
        ctrl = event.GetEventObject()
        text = ctrl.GetValue()
        ctrl.SetValue("")
        if ctrl is self.password:
            # Never echoed, spoken, stored or replayed.
            self.conn.send_line(text)
            return
        self.send_command(text)
        if text.strip() and (not self.history or self.history[-1] != text):
            self.history.append(text)
            del self.history[:-HISTORY_MAX]
        self.hist_pos = None

    def send_command(self, text, echo_text=None):
        self.echo(echo_text if echo_text is not None else text)
        if not self.conn.send_line(text):
            self.notice(self.tr("state.closed"))

    def on_input_key(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_UP, wx.WXK_DOWN) and not event.HasAnyModifiers():
            if not self.history:
                return
            if self.hist_pos is None:
                self.hist_pos = len(self.history)
            self.hist_pos += -1 if key == wx.WXK_UP else 1
            self.hist_pos = max(0, min(len(self.history), self.hist_pos))
            value = self.history[self.hist_pos] if self.hist_pos < len(self.history) else ""
            self.input.SetValue(value)
            self.input.SetInsertionPointEnd()
            return
        if key == wx.WXK_ESCAPE:
            self.input.SetValue("")
            self.hist_pos = None
            return
        event.Skip()

    def set_password_mode(self, on):
        if on == self.password.IsShown():
            return
        focus_was_input = wx.Window.FindFocus() in (self.input, self.password)
        self.password.Show(on)
        self.input.Show(not on)
        self.input_label.SetLabel(self.tr("password.name") if on else self.tr("input.name"))
        self.panel.Layout()
        if focus_was_input:
            (self.password if on else self.input).SetFocus()
        if not on:
            self.password.SetValue("")

    def on_f6(self, event):
        if wx.Window.FindFocus() is self.output:
            (self.password if self.password.IsShown() else self.input).SetFocus()
        else:
            self.output.SetFocus()
            self.output.SetInsertionPoint(self.output.GetLastPosition())

    def on_output_key(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not event.HasAnyModifiers():
            self.line_menu(always_menu=False)
            return
        event.Skip()

    def on_output_char(self, event):
        # Typing in the output goes to the command field.
        code = event.GetUnicodeKey()
        if code >= 32 and not event.ControlDown() and not event.AltDown():
            target = self.password if self.password.IsShown() else self.input
            target.SetFocus()
            target.WriteText(chr(code))
            return
        event.Skip()

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
        p = self.prompt
        if "hit" in p:
            self.SetStatusText(self.status_text())

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
        self.SetStatusText(text)

    def toggle_speech(self):
        self.prefs["speech"] = not self.prefs.get("speech")
        self.speech_item.Check(self.prefs["speech"])
        self.say(self.tr("speech.on" if self.prefs["speech"] else "speech.off"))

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
        self.output_label.SetLabel(self.tr("output.name"))
        self.output.SetName(self.tr("output.name"))
        self.input.SetName(self.tr("input.name"))
        self.password.SetName(self.tr("password.name"))
        self.input_label.SetLabel(self.tr("password.name") if self.password.IsShown() else self.tr("input.name"))
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
