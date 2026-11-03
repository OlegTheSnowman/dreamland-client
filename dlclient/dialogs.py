"""Windows for triggers, key macros, aliases, variables and game settings.

Every window is plain wx controls with a visible label in front of each one,
so a screen reader names every field.
"""

import re

import wx

from .scripting import SCOPES, VAR_NAME, Aliases, compile_trigger, key_name

COLOURS = [
    ("#ff4040", {"en": "red", "ua": "червоний", "ru": "красный"}),
    ("#40c040", {"en": "green", "ua": "зелений", "ru": "зеленый"}),
    ("#4080ff", {"en": "blue", "ua": "синій", "ru": "синий"}),
    ("#ffd700", {"en": "yellow", "ua": "жовтий", "ru": "желтый"}),
    ("#ff8c00", {"en": "orange", "ua": "помаранчевий", "ru": "оранжевый"}),
    ("#c060ff", {"en": "purple", "ua": "фіолетовий", "ru": "фиолетовый"}),
    ("#00c0c0", {"en": "cyan", "ua": "блакитний", "ru": "голубой"}),
    ("#ffffff", {"en": "white", "ua": "білий", "ru": "белый"}),
]


def labelled(parent, sizer, label, ctrl, expand=True):
    t = wx.StaticText(parent, label=label)
    sizer.Add(t, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
    sizer.Add(ctrl, 1 if expand == "grow" else 0, wx.EXPAND | wx.ALL, 6)
    ctrl.SetName(label.replace("&", ""))
    return ctrl


def ok_cancel(dlg, sizer, tr):
    ok = wx.Button(dlg, wx.ID_OK, tr("ok"))
    cancel = wx.Button(dlg, wx.ID_CANCEL, tr("cancel"))
    ok.SetDefault()
    b = wx.StdDialogButtonSizer()
    b.AddButton(ok)
    b.AddButton(cancel)
    b.Realize()
    sizer.Add(b, 0, wx.ALL | wx.ALIGN_RIGHT, 6)
    return ok


def message(parent, text, title):
    wx.MessageBox(text, title, wx.OK | wx.ICON_INFORMATION, parent)


# ------------------------------------------------------------ list manager
class ListManager(wx.Dialog):
    """A list with Add, Edit and Delete. Subclasses fill in the specifics."""

    title_key = list_key = ""

    def __init__(self, parent, tr):
        super().__init__(parent, title=tr(self.title_key), size=wx.Size(700, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr = tr
        self.rows = []
        s = wx.BoxSizer(wx.VERTICAL)
        self.info = wx.StaticText(self, label="")
        s.Add(self.info, 0, wx.ALL, 6)
        self.list = labelled(self, s, tr(self.list_key), wx.ListBox(self), expand="grow")
        btns = wx.BoxSizer(wx.HORIZONTAL)
        self.add_btn = wx.Button(self, label=tr("list.add"))
        self.edit_btn = wx.Button(self, label=tr("list.edit"))
        self.del_btn = wx.Button(self, label=tr("list.delete"))
        close = wx.Button(self, wx.ID_CANCEL, tr("list.close"))
        for b in (self.add_btn, self.edit_btn, self.del_btn, close):
            btns.Add(b, 0, wx.ALL, 4)
        s.Add(btns, 0, wx.ALL, 2)
        self.SetSizer(s)
        self.add_btn.Bind(wx.EVT_BUTTON, lambda e: self.on_add())
        self.edit_btn.Bind(wx.EVT_BUTTON, lambda e: self.on_edit())
        self.del_btn.Bind(wx.EVT_BUTTON, lambda e: self.on_delete())
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.on_edit())
        self.list.Bind(wx.EVT_KEY_DOWN, self.on_list_key)
        self.refresh()
        self.list.SetFocus()

    def on_list_key(self, event):
        k = event.GetKeyCode()
        if k == wx.WXK_DELETE:
            return self.on_delete()
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            return self.on_edit()
        event.Skip()

    def refresh(self, select=None):
        old = self.list.GetSelection()
        self.rows = self.load_rows()
        self.list.Set([self.describe(r) for r in self.rows] or [self.tr("list.empty")])
        n = len(self.rows)
        ready = self.ready()
        self.add_btn.Enable(ready)
        self.edit_btn.Enable(ready and n > 0)
        self.del_btn.Enable(ready and n > 0)
        self.info.SetLabel("" if ready else self.tr("list.wait"))
        if n:
            idx = select if select is not None else old
            self.list.SetSelection(max(0, min(n - 1, idx if idx != wx.NOT_FOUND else 0)))
        self.Layout()

    def selected(self):
        i = self.list.GetSelection()
        return self.rows[i] if 0 <= i < len(self.rows) else None

    def scope_name(self, scope):
        return self.tr("scope." + scope)

    # Subclasses
    def ready(self):
        return True

    def load_rows(self):
        return []

    def describe(self, row):
        return str(row)

    def on_add(self):
        pass

    def on_edit(self):
        pass

    def on_delete(self):
        pass


def scope_choice(dlg, sizer, tr, store_has_account, current):
    scopes = [s for s in SCOPES if s == "char" or store_has_account]
    ch = labelled(dlg, sizer, tr("scope.label"), wx.Choice(dlg, choices=[tr("scope." + s) for s in scopes]))
    ch.SetSelection(scopes.index(current) if current in scopes else len(scopes) - 1)
    return ch, scopes


# --------------------------------------------------------------- triggers
class TriggerEdit(wx.Dialog):
    def __init__(self, parent, tr, sound, trig, scope, has_account):
        super().__init__(parent, title=tr("tr.edit"), size=wx.Size(600, 620),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr, self.sound = tr, sound
        trig = trig or {}
        s = wx.BoxSizer(wx.VERTICAL)
        self.pattern = labelled(self, s, tr("tr.pattern"), wx.TextCtrl(self, value=trig.get("pattern", "")))
        self.regex = wx.CheckBox(self, label=tr("tr.regex"))
        self.regex.SetValue(bool(trig.get("regex")))
        s.Add(self.regex, 0, wx.ALL, 6)
        self.enabled = wx.CheckBox(self, label=tr("tr.enabled"))
        self.enabled.SetValue(trig.get("on", True) is not False)
        s.Add(self.enabled, 0, wx.ALL, 6)
        self.cmd = labelled(self, s, tr("tr.cmd"), wx.TextCtrl(self, value=trig.get("cmd", "")))

        lang = tr.lang
        self.sounds = [""] + [x["name"] for x in sound.library]
        names = [tr("tr.sound.none")] + [
            "%s (%s)" % ((x.get("label") or {}).get(lang) or x["name"], x["name"]) for x in sound.library]
        self.sound_ch = labelled(self, s, tr("tr.sound"), wx.Choice(self, choices=names))
        cur = (trig.get("sound") or {}).get("name", "") if isinstance(trig.get("sound"), dict) else ""
        self.sound_ch.SetSelection(self.sounds.index(cur) if cur in self.sounds else 0)
        play = wx.Button(self, label=tr("tr.sound.play"))
        play.Bind(wx.EVT_BUTTON, lambda e: self.preview())
        s.Add(play, 0, wx.ALL, 6)

        hl = trig.get("hl") if isinstance(trig.get("hl"), dict) else None
        self.hl_modes = ["", "line", "match"]
        self.hl = labelled(self, s, tr("tr.hl"), wx.Choice(
            self, choices=[tr("tr.hl.none"), tr("tr.hl.line"), tr("tr.hl.match")]))
        self.hl.SetSelection(self.hl_modes.index(hl.get("mode")) if hl and hl.get("mode") in self.hl_modes else 0)
        self.colours = [c for c, _ in COLOURS]
        names = [n.get(lang, n["en"]) for _, n in COLOURS]
        colour = (hl or {}).get("color", COLOURS[3][0]).lower()
        if colour not in self.colours:
            self.colours.append(colour)
            names.append(colour)
        self.colour = labelled(self, s, tr("tr.color"), wx.Choice(self, choices=names))
        self.colour.SetSelection(self.colours.index(colour))

        self.scope, self.scopes = scope_choice(self, s, tr, has_account, scope)
        ok = ok_cancel(self, s, tr)
        ok.Bind(wx.EVT_BUTTON, self.on_ok)
        self.SetSizer(s)
        self.trig = dict(trig)
        self.pattern.SetFocus()

    def preview(self):
        i = self.sound_ch.GetSelection()
        if i > 0:
            self.sound.preview(self.sounds[i])

    def on_ok(self, event):
        t = self.trig
        t["pattern"] = self.pattern.GetValue()
        t["regex"] = self.regex.GetValue()
        t["on"] = self.enabled.GetValue()
        t["cmd"] = self.cmd.GetValue()
        i = self.sound_ch.GetSelection()
        old = t.get("sound") if isinstance(t.get("sound"), dict) else {}
        t["sound"] = {"name": self.sounds[i], "V": old.get("V", 100)} if i > 0 else None
        mode = self.hl_modes[self.hl.GetSelection()]
        t["hl"] = {"mode": mode, "color": self.colours[self.colour.GetSelection()]} if mode else None
        t.setdefault("act", t["pattern"])
        if compile_trigger(t) is None:
            message(self, self.tr("tr.bad"), self.tr("tr.edit"))
            self.pattern.SetFocus()
            return
        self.result_scope = self.scopes[self.scope.GetSelection()]
        self.EndModal(wx.ID_OK)


class TriggersDialog(ListManager):
    title_key, list_key = "tr.title", "tr.list"

    def __init__(self, parent, tr, store, sound):
        self.store, self.sound = store, sound
        super().__init__(parent, tr)

    def ready(self):
        return self.store.known

    def load_rows(self):
        return self.store.all()

    def describe(self, row):
        scope, t = row
        parts = [t.get("pattern", "")]
        if t.get("cmd"):
            parts.append("-> " + t["cmd"])
        if isinstance(t.get("sound"), dict) and t["sound"].get("name"):
            parts.append(self.tr("tr.sound") + " " + t["sound"]["name"])
        parts.append(self.tr("on") if t.get("on", True) is not False else self.tr("off"))
        parts.append(self.scope_name(scope))
        return ", ".join(parts)

    def edit(self, scope, trig):
        dlg = TriggerEdit(self, self.tr, self.sound, trig, scope or ("acct" if self.store.account else "char"),
                          self.store.account)
        if dlg.ShowModal() == wx.ID_OK:
            new = dlg.trig
            if not new.get("id"):
                from .scripting import new_id
                new["id"] = new_id()
            target = dlg.result_scope
            if scope and scope != target:
                self.store.set_list(scope, [x for x in self.store.lists[scope] if x is not trig])
            lst = list(self.store.lists[target])
            if trig is not None and scope == target:
                lst = [new if x is trig else x for x in lst]
            else:
                if len(lst) >= self.store.max_items:
                    message(self, self.tr("list.full"), self.tr(self.title_key))
                    dlg.Destroy()
                    return
                lst.append(new)
            self.store.set_list(target, lst)
            self.refresh()
        dlg.Destroy()

    def on_add(self):
        self.edit(None, None)

    def on_edit(self):
        row = self.selected()
        if row:
            self.edit(row[0], row[1])

    def on_delete(self):
        row = self.selected()
        if row:
            scope, t = row
            self.store.set_list(scope, [x for x in self.store.lists[scope] if x is not t])
            self.refresh()


# ----------------------------------------------------------------- macros
class KeyCapture(wx.TextCtrl):
    """A read-only field that takes the name of the next key combination pressed."""

    def __init__(self, parent, tr, value, say):
        super().__init__(parent, value=value or tr("mc.key.none"), style=wx.TE_READONLY)
        self.tr, self.key, self.say = tr, value or "", say
        self.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self.Bind(wx.EVT_CHAR, lambda e: None)

    def on_key(self, event):
        k = event.GetKeyCode()
        if k == wx.WXK_TAB and not event.ControlDown() and not event.AltDown():
            return event.Skip()
        if k == wx.WXK_BACK and not event.HasAnyModifiers():
            self.key = ""
            self.SetValue(self.tr("mc.key.none"))
            self.say(self.tr("mc.key.none"))
            return
        name = key_from_event(event)
        if name:
            self.key = name
            self.SetValue(name)
            self.say(name)


_NUMPAD = {}


def _numpad_table():
    if _NUMPAD:
        return _NUMPAD
    for i in range(10):
        _NUMPAD[getattr(wx, "WXK_NUMPAD%d" % i)] = "kp%d" % i
    # NumLock off: the keypad reports its second meaning, still the same key.
    for code, name in (("WXK_NUMPAD_INSERT", "kp0"), ("WXK_NUMPAD_END", "kp1"), ("WXK_NUMPAD_DOWN", "kp2"),
                       ("WXK_NUMPAD_PAGEDOWN", "kp3"), ("WXK_NUMPAD_LEFT", "kp4"), ("WXK_NUMPAD_BEGIN", "kp5"),
                       ("WXK_NUMPAD_RIGHT", "kp6"), ("WXK_NUMPAD_HOME", "kp7"), ("WXK_NUMPAD_UP", "kp8"),
                       ("WXK_NUMPAD_PAGEUP", "kp9"), ("WXK_NUMPAD_DELETE", "kp."),
                       ("WXK_NUMPAD_DECIMAL", "kp."), ("WXK_NUMPAD_MULTIPLY", "kp*"),
                       ("WXK_NUMPAD_ADD", "kp+"), ("WXK_NUMPAD_SUBTRACT", "kp-"), ("WXK_NUMPAD_DIVIDE", "kp/")):
        _NUMPAD[getattr(wx, code)] = name
    return _NUMPAD


def key_from_event(event):
    """mudjs-style key name for a wx key event, or None (bare modifiers, unknown keys)."""
    if event.MetaDown():
        return None
    code = event.GetKeyCode()
    if code in (wx.WXK_SHIFT, wx.WXK_CONTROL, wx.WXK_ALT, wx.WXK_WINDOWS_LEFT, wx.WXK_WINDOWS_RIGHT):
        return None
    numpad = _numpad_table().get(code)
    vk = event.GetRawKeyCode()
    return key_name(vk, numpad, event.ControlDown(), event.AltDown(), event.ShiftDown())


def key_fallback_from_event(event):
    """For a keypad press, the name an older macro on the arrow would have used."""
    numpad = _numpad_table().get(event.GetKeyCode())
    if not numpad:
        return None
    name = key_name(event.GetRawKeyCode(), None, event.ControlDown(), event.AltDown(), event.ShiftDown())
    return name if name and not name.endswith(numpad) else None


class MacroEdit(wx.Dialog):
    def __init__(self, parent, tr, macro, scope, has_account, say):
        super().__init__(parent, title=tr("mc.edit"), size=wx.Size(560, 330))
        self.tr = tr
        macro = macro or {}
        s = wx.BoxSizer(wx.VERTICAL)
        self.key = labelled(self, s, tr("mc.key"), KeyCapture(self, tr, macro.get("key", ""), say))
        self.cmd = labelled(self, s, tr("mc.cmd"), wx.TextCtrl(self, value=macro.get("cmd", "")))
        self.scope, self.scopes = scope_choice(self, s, tr, has_account, scope)
        ok = ok_cancel(self, s, tr)
        ok.Bind(wx.EVT_BUTTON, self.on_ok)
        self.SetSizer(s)
        self.key.SetFocus()

    def on_ok(self, event):
        if not self.key.key:
            message(self, self.tr("mc.badkey"), self.tr("mc.edit"))
            self.key.SetFocus()
            return
        self.result = {"key": self.key.key, "cmd": self.cmd.GetValue()}
        self.result_scope = self.scopes[self.scope.GetSelection()]
        self.EndModal(wx.ID_OK)


class MacrosDialog(ListManager):
    title_key, list_key = "mc.title", "mc.list"

    def __init__(self, parent, tr, store, say):
        self.store, self.say = store, say
        super().__init__(parent, tr)

    def ready(self):
        return self.store.known

    def load_rows(self):
        return self.store.all()

    def describe(self, row):
        scope, m = row
        return "%s: %s, %s" % (m["key"], m["cmd"], self.scope_name(scope))

    def edit(self, scope, macro):
        dlg = MacroEdit(self, self.tr, macro, scope or ("acct" if self.store.account else "char"),
                        self.store.account, self.say)
        if dlg.ShowModal() == wx.ID_OK:
            new, target = dlg.result, dlg.result_scope
            if scope:
                self.store.set_list(scope, [x for x in self.store.lists[scope] if x is not macro])
            lst = [x for x in self.store.lists[target] if x["key"] != new["key"]]
            if len(lst) >= self.store.max_items:
                message(self, self.tr("list.full"), self.tr(self.title_key))
            else:
                self.store.set_list(target, lst + [new])
            self.refresh()
        dlg.Destroy()

    def on_add(self):
        self.edit(None, None)

    def on_edit(self):
        row = self.selected()
        if row:
            self.edit(row[0], row[1])

    def on_delete(self):
        row = self.selected()
        if row:
            scope, m = row
            self.store.set_list(scope, [x for x in self.store.lists[scope] if x is not m])
            self.refresh()


# ---------------------------------------------------------------- aliases
class AliasEdit(wx.Dialog):
    def __init__(self, parent, tr, alias, scope, has_account):
        super().__init__(parent, title=tr("al.edit"), size=wx.Size(560, 330))
        self.tr = tr
        alias = alias or {}
        s = wx.BoxSizer(wx.VERTICAL)
        self.name = labelled(self, s, tr("al.name"), wx.TextCtrl(self, value=alias.get("name", "")))
        self.body = labelled(self, s, tr("al.body"), wx.TextCtrl(self, value=alias.get("body", "")))
        self.scope, self.scopes = scope_choice(self, s, tr, has_account, scope)
        ok = ok_cancel(self, s, tr)
        ok.Bind(wx.EVT_BUTTON, self.on_ok)
        self.SetSizer(s)
        self.name.SetFocus()

    def on_ok(self, event):
        name = self.name.GetValue().strip()
        if Aliases.bad_name(name):
            message(self, self.tr("al.badname"), self.tr("al.edit"))
            self.name.SetFocus()
            return
        self.result = {"name": name, "body": self.body.GetValue()}
        self.result_scope = self.scopes[self.scope.GetSelection()]
        self.EndModal(wx.ID_OK)


class AliasesDialog(ListManager):
    title_key, list_key = "al.title", "al.list"

    def __init__(self, parent, tr, store):
        self.store = store
        super().__init__(parent, tr)

    def ready(self):
        return self.store.known

    def load_rows(self):
        return [("char", a) for a in self.store.char] + [("acct", a) for a in self.store.acct]

    def describe(self, row):
        scope, a = row
        return "%s: %s, %s" % (a["name"], a["body"], self.scope_name(scope))

    def edit(self, scope, alias):
        dlg = AliasEdit(self, self.tr, alias, scope or "char", self.store.account)
        if dlg.ShowModal() == wx.ID_OK:
            new, target = dlg.result, dlg.result_scope
            old_name = alias["name"] if alias else None
            if scope == "acct" and (target != "acct"):
                self.store.set_acct([x for x in self.store.acct if x is not alias])
            if scope == "char" and target != "char":
                self.store.remove_char(old_name)
            if target == "char":
                self.store.set_char(old_name if scope == "char" else None, new["name"], new["body"])
            else:
                lst = [x for x in self.store.acct if x is not alias and x["name"] != new["name"]]
                self.store.set_acct(lst + [new])
            # The character's list comes back from the server a moment later.
            wx.CallLater(800, self.refresh)
            self.refresh()
        dlg.Destroy()

    def on_add(self):
        self.edit(None, None)

    def on_edit(self):
        row = self.selected()
        if row:
            self.edit(row[0], row[1])

    def on_delete(self):
        row = self.selected()
        if not row:
            return
        scope, a = row
        if scope == "char":
            self.store.remove_char(a["name"])
            wx.CallLater(800, self.refresh)
        else:
            self.store.set_acct([x for x in self.store.acct if x is not a])
        self.refresh()


# -------------------------------------------------------------- variables
class VarEdit(wx.Dialog):
    def __init__(self, parent, tr, name, value):
        super().__init__(parent, title=tr("var.edit"), size=wx.Size(500, 260))
        self.tr = tr
        s = wx.BoxSizer(wx.VERTICAL)
        self.name = labelled(self, s, tr("var.name"), wx.TextCtrl(self, value=name or ""))
        self.value = labelled(self, s, tr("var.value"), wx.TextCtrl(self, value=value or ""))
        ok = ok_cancel(self, s, tr)
        ok.Bind(wx.EVT_BUTTON, self.on_ok)
        self.SetSizer(s)
        self.name.SetFocus()

    def on_ok(self, event):
        if not VAR_NAME.match(self.name.GetValue().strip()):
            message(self, self.tr("var.badname"), self.tr("var.edit"))
            self.name.SetFocus()
            return
        self.result = (self.name.GetValue().strip(), self.value.GetValue())
        self.EndModal(wx.ID_OK)


class VarsDialog(ListManager):
    title_key, list_key = "var.title", "var.list"

    def __init__(self, parent, tr, variables):
        self.vars = variables
        super().__init__(parent, tr)

    def load_rows(self):
        return sorted(self.vars.items())

    def describe(self, row):
        return "$%s: %s" % row

    def edit(self, name, value):
        dlg = VarEdit(self, self.tr, name, value)
        if dlg.ShowModal() == wx.ID_OK:
            new_name, new_value = dlg.result
            if name and name != new_name:
                self.vars.pop(name, None)
            self.vars[new_name] = new_value
            self.refresh()
        dlg.Destroy()

    def on_add(self):
        self.edit(None, None)

    def on_edit(self):
        row = self.selected()
        if row:
            self.edit(*row)

    def on_delete(self):
        row = self.selected()
        if row:
            self.vars.pop(row[0], None)
            self.refresh()


# ---------------------------------------------------------- game settings
class SettingsDialog(wx.Dialog):
    """Built from the server's config_schema, like the web client's settings window.

    Pages are in a list; picking one fills the panel with its options. A change
    goes to the server at once as config_set and the field follows the answer.
    """

    def __init__(self, parent, tr, rpc, say):
        super().__init__(parent, title=tr("cfg.title"), size=wx.Size(820, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr, self.rpc, self.say = tr, rpc, say
        self.schema, self.values, self.pages, self.controls = None, {}, [], {}
        s = wx.BoxSizer(wx.HORIZONTAL)
        left = wx.BoxSizer(wx.VERTICAL)
        self.page_list = labelled(self, left, tr("cfg.pages"), wx.ListBox(self, size=wx.Size(220, -1)),
                                  expand="grow")
        s.Add(left, 0, wx.EXPAND)
        self.panel = wx.ScrolledWindow(self, style=wx.TAB_TRAVERSAL)
        self.panel.SetScrollRate(0, 20)
        s.Add(self.panel, 1, wx.EXPAND | wx.ALL, 6)
        outer = wx.BoxSizer(wx.VERTICAL)
        self.info = wx.StaticText(self, label=tr("cfg.asking"))
        outer.Add(self.info, 0, wx.ALL, 6)
        outer.Add(s, 1, wx.EXPAND)
        close = wx.Button(self, wx.ID_CANCEL, tr("list.close"))
        outer.Add(close, 0, wx.ALL | wx.ALIGN_RIGHT, 6)
        self.SetSizer(outer)
        self.page_list.Bind(wx.EVT_LISTBOX, lambda e: self.show_page(self.page_list.GetSelection()))
        self.page_list.SetFocus()

    def set_waiting(self, text):
        self.info.SetLabel(text)

    def on_schema(self, body):
        self.schema = body or {}
        self.values = dict(self.schema.get("values") or {})
        self.pages = []
        for section in self.schema.get("sections") or []:
            for page in section.get("pages") or []:
                if page.get("options"):
                    self.pages.append((section.get("label", ""), page))
        if not self.pages:
            self.info.SetLabel(self.tr("cfg.missing"))
            return
        self.info.SetLabel("")
        self.page_list.Set(["%s: %s" % (sec, p.get("label", p.get("key"))) for sec, p in self.pages])
        self.page_list.SetSelection(0)
        self.show_page(0)

    def show_page(self, i):
        if not (0 <= i < len(self.pages)):
            return
        self.panel.DestroyChildren()
        self.controls = {}
        s = wx.BoxSizer(wx.VERTICAL)
        page = self.pages[i][1]
        if page.get("subtitle"):
            s.Add(wx.StaticText(self.panel, label=page["subtitle"]), 0, wx.ALL, 6)
        for opt in page.get("options") or []:
            self._add_option(s, opt)
        self.panel.SetSizer(s)
        self.panel.FitInside()
        self.panel.Layout()

    def _add_option(self, s, opt):
        key, kind = opt.get("key"), opt.get("type")
        if not key:
            return
        label = opt.get("label") or key
        hint = opt.get("hint") or ""
        value = self.values.get(key)
        p = self.panel
        if kind == "bool":
            c = wx.CheckBox(p, label=label)
            c.SetValue(bool(value) and value not in ("0", "off", "false"))
            c.Bind(wx.EVT_CHECKBOX, lambda e, k=key, c=c: self.send(k, "on" if c.GetValue() else "off"))
            s.Add(c, 0, wx.ALL, 6)
        elif kind == "enum":
            vals = opt.get("values") or []
            names = ["%s (%s)" % (v.get("label", v.get("value")), v.get("desc")) if v.get("desc")
                     else str(v.get("label", v.get("value"))) for v in vals]
            c = labelled(p, s, label, wx.Choice(p, choices=names))
            keys = [str(v.get("value")) for v in vals]
            if str(value) in keys:
                c.SetSelection(keys.index(str(value)))
            c.Bind(wx.EVT_CHOICE, lambda e, k=key, c=c, keys=keys: self.send(k, keys[c.GetSelection()]))
        elif kind == "int":
            lo, hi = int(opt.get("min", 0)), int(opt.get("max", 1000))
            off = opt.get("offValue")
            if off is not None:
                lo = min(lo, int(off))
            c = labelled(p, s, label, wx.SpinCtrl(p, min=lo, max=hi, initial=int(value or 0)
                                                  if str(value or "0").lstrip("-").isdigit() else lo))
            apply = wx.Button(p, label=self.tr("cfg.apply") + ": " + label)
            apply.Bind(wx.EVT_BUTTON, lambda e, k=key, c=c: self.send(k, str(c.GetValue())))
            s.Add(apply, 0, wx.LEFT | wx.BOTTOM, 6)
        elif kind == "string":
            c = labelled(p, s, label, wx.TextCtrl(p, value=str(value or ""), style=wx.TE_PROCESS_ENTER))
            apply = wx.Button(p, label=self.tr("cfg.apply") + ": " + label)
            go = (lambda e, k=key, c=c: self.send(k, c.GetValue()))
            apply.Bind(wx.EVT_BUTTON, go)
            c.Bind(wx.EVT_TEXT_ENTER, go)
            s.Add(apply, 0, wx.LEFT | wx.BOTTOM, 6)
        else:
            return
        if hint:
            c.SetHelpText(hint)
            c.SetToolTip(hint)
            h = wx.StaticText(p, label=hint)
            s.Add(h, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.controls[key] = (c, opt)

    def send(self, key, value):
        self.rpc("config_set", key, value)

    def _show_value(self, key, value):
        self.values[key] = value
        if key not in self.controls:
            return
        c, opt = self.controls[key]
        kind = opt.get("type")
        if kind == "bool":
            c.SetValue(bool(value) and value not in ("0", "off", "false"))
        elif kind == "enum":
            keys = [str(v.get("value")) for v in opt.get("values") or []]
            if str(value) in keys:
                c.SetSelection(keys.index(str(value)))
        elif kind == "int" and str(value).lstrip("-").isdigit():
            c.SetValue(int(value))
        elif kind == "string":
            c.ChangeValue(str(value))

    def on_result(self, body):
        if not isinstance(body, dict) or not body.get("key"):
            return
        if body.get("ok"):
            self._show_value(body["key"], body.get("value"))
        else:
            # Put the field back where the server has it, then say why.
            self._show_value(body["key"], self.values.get(body["key"]))
            self.say(self.tr("cfg.refused", body.get("reason") or body.get("error") or ""))

    def on_changed(self, body):
        if isinstance(body, dict) and body.get("key"):
            self._show_value(body["key"], body.get("value"))
