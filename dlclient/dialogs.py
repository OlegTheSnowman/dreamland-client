import html
import re
import time

import wx

from .access import NamedAccessible
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
    ctrl._acc = NamedAccessible(ctrl, label.replace("&", ""))
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


class ListManager(wx.Dialog):
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
            lst = list(self.store.lists[target])
            if trig is not None and scope == target:
                lst = [new if x is trig else x for x in lst]
            else:
                if len(lst) >= self.store.max_items:
                    message(self, self.tr("list.full"), self.tr(self.title_key))
                    dlg.Destroy()
                    return
                lst.append(new)
                if scope:
                    self.store.set_list(scope, [x for x in self.store.lists[scope] if x is not trig])
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


class KeyCapture(wx.TextCtrl):
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
    for code, name in (("WXK_NUMPAD_INSERT", "kp0"), ("WXK_NUMPAD_END", "kp1"), ("WXK_NUMPAD_DOWN", "kp2"),
                       ("WXK_NUMPAD_PAGEDOWN", "kp3"), ("WXK_NUMPAD_LEFT", "kp4"), ("WXK_NUMPAD_BEGIN", "kp5"),
                       ("WXK_NUMPAD_RIGHT", "kp6"), ("WXK_NUMPAD_HOME", "kp7"), ("WXK_NUMPAD_UP", "kp8"),
                       ("WXK_NUMPAD_PAGEUP", "kp9"), ("WXK_NUMPAD_DELETE", "kp."),
                       ("WXK_NUMPAD_DECIMAL", "kp."), ("WXK_NUMPAD_MULTIPLY", "kp*"),
                       ("WXK_NUMPAD_ADD", "kp+"), ("WXK_NUMPAD_SUBTRACT", "kp-"), ("WXK_NUMPAD_DIVIDE", "kp/")):
        _NUMPAD[getattr(wx, code)] = name
    return _NUMPAD


def key_from_event(event):
    if event.MetaDown():
        return None
    code = event.GetKeyCode()
    if code in (wx.WXK_SHIFT, wx.WXK_CONTROL, wx.WXK_ALT, wx.WXK_WINDOWS_LEFT, wx.WXK_WINDOWS_RIGHT):
        return None
    numpad = _numpad_table().get(code)
    vk = event.GetRawKeyCode()
    return key_name(vk, numpad, event.ControlDown(), event.AltDown(), event.ShiftDown())


def key_fallback_from_event(event):
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
            lst = [x for x in self.store.lists[target] if x["key"] != new["key"] and x is not macro]
            if len(lst) >= self.store.max_items:
                message(self, self.tr("list.full"), self.tr(self.title_key))
            else:
                if scope and scope != target:
                    self.store.set_list(scope, [x for x in self.store.lists[scope] if x is not macro])
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


class SettingsDialog(wx.Dialog):
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
        if not key or kind not in ("bool", "enum", "int", "string", "account"):
            return
        p = self.panel
        label = opt.get("label") or key
        value = self.values.get(key)
        row = {"opt": opt, "ctrls": [], "label": label}

        title = wx.StaticText(p, label=label)
        title.SetFont(title.GetFont().Bold())
        s.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)

        if kind == "bool":
            c = wx.CheckBox(p, label=label)
            c.Bind(wx.EVT_CHECKBOX, lambda e, k=key, c=c: self.send(k, "on" if c.GetValue() else "off"))
            s.Add(c, 0, wx.ALL, 6)
            row["main"] = c
        elif kind == "enum":
            vals = opt.get("values") or []
            names = [("%s: %s" % (v.get("label", v.get("value")), v.get("desc"))) if v.get("desc")
                     else str(v.get("label", v.get("value"))) for v in vals]
            c = wx.Choice(p, choices=names)
            keys = [str(v.get("value")) for v in vals]
            c.Bind(wx.EVT_CHOICE, lambda e, k=key, c=c, keys=keys: self.send(k, keys[c.GetSelection()]))
            s.Add(c, 0, wx.EXPAND | wx.ALL, 6)
            row["main"], row["keys"] = c, keys
        elif kind == "int":
            lo, hi = int(opt.get("min", 0)), int(opt.get("max", 100))
            off = opt.get("offValue")
            c = wx.TextCtrl(p, style=wx.TE_PROCESS_ENTER)
            go = (lambda e, k=key, c=c: self.send_int(k, c))
            c.Bind(wx.EVT_TEXT_ENTER, go)
            line = wx.BoxSizer(wx.HORIZONTAL)
            line.Add(c, 1, wx.RIGHT, 6)
            apply = wx.Button(p, label=self.tr("cfg.apply"))
            apply.Bind(wx.EVT_BUTTON, go)
            line.Add(apply, 0, wx.RIGHT, 6)
            row["ctrls"].append((apply, self.tr("cfg.apply") + ": " + label))
            if off is not None:
                b = wx.Button(p, label=self.tr("cfg.turnoff"))
                b.Bind(wx.EVT_BUTTON, lambda e, k=key, off=off: self.send(k, str(off)))
                line.Add(b, 0)
                row["ctrls"].append((b, self.tr("cfg.turnoff") + ": " + label))
            s.Add(line, 0, wx.EXPAND | wx.ALL, 6)
            row["main"] = c
            row["range"] = self.tr("cfg.range", lo, hi)
        elif kind == "string":
            c = wx.TextCtrl(p, style=wx.TE_PROCESS_ENTER)
            if opt.get("placeholder"):
                c.SetHint(opt["placeholder"])
            go = (lambda e, k=key, c=c: self.send(k, c.GetValue().strip()))
            c.Bind(wx.EVT_TEXT_ENTER, go)
            line = wx.BoxSizer(wx.HORIZONTAL)
            line.Add(c, 1, wx.RIGHT, 6)
            apply = wx.Button(p, label=self.tr("cfg.apply"))
            apply.Bind(wx.EVT_BUTTON, go)
            line.Add(apply, 0, wx.RIGHT, 6)
            clear = wx.Button(p, label=self.tr("cfg.clear"))
            clear.Bind(wx.EVT_BUTTON, lambda e, k=key: self.send(k, ""))
            line.Add(clear, 0)
            s.Add(line, 0, wx.EXPAND | wx.ALL, 6)
            row["ctrls"] += [(apply, self.tr("cfg.apply") + ": " + label),
                             (clear, self.tr("cfg.clear") + ": " + label)]
            row["main"] = c
            if opt.get("placeholder"):
                row["range"] = self.tr("cfg.example", opt["placeholder"])
        else:
            c = wx.TextCtrl(p, style=wx.TE_READONLY)
            s.Add(c, 0, wx.EXPAND | wx.ALL, 6)
            row["main"] = c
            line = wx.BoxSizer(wx.HORIZONTAL)
            for action in opt.get("actions") or []:
                alabel = action.get("label") or str(action.get("value"))
                if isinstance(alabel, dict):
                    alabel = alabel.get(self.tr.lang) or alabel.get("en") or ""
                b = wx.Button(p, label=alabel)
                b.Bind(wx.EVT_BUTTON, lambda e, k=key, v=action.get("value", ""): self.send(k, str(v)))
                line.Add(b, 0, wx.RIGHT, 6)
                row["ctrls"].append((b, alabel + ": " + label))
            s.Add(line, 0, wx.ALL, 6)

        row["status"] = wx.StaticText(p, label="")
        s.Add(row["status"], 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        row["acc"] = NamedAccessible(row["main"], label, self.long_help(opt))
        for ctrl, name in row["ctrls"]:
            ctrl._acc = NamedAccessible(ctrl, name, self.long_help(opt))
        self.controls[key] = row
        self._show_value(key, value)

    def long_help(self, opt):
        parts = [opt.get("hint") or "", opt.get("help") or ""]
        for ex in opt.get("examples") or []:
            text = re.sub(r"<[^>]+>", "", str(ex.get("text") or ""))
            parts.append("%s: %s" % (ex.get("label") or self.tr("cfg.example", ""), html.unescape(text)))
        return "\n".join(x for x in parts if x)

    def describe(self, opt, value):
        kind = opt.get("type")
        hint = opt.get("hint") or ""
        if kind == "bool":
            return (opt.get("on") if self._on(value) else opt.get("off")) or hint
        if kind == "enum":
            for v in opt.get("values") or []:
                if str(v.get("value")) == str(value):
                    return v.get("desc") or v.get("label") or hint
            return hint
        if kind == "int":
            off = opt.get("offValue", 0)
            try:
                n = int(value)
            except (TypeError, ValueError):
                return opt.get("descEmpty") or hint
            if n == off:
                return opt.get("descEmpty") or hint
            return (opt.get("desc") or hint).replace("%d", str(n))
        held = (value or {}).get("username") if kind == "account" and isinstance(value, dict) else value
        if not held:
            return opt.get("descEmpty") or hint
        return (opt.get("desc") or hint).replace("%s", str(held))

    @staticmethod
    def _on(value):
        return bool(value) and str(value).lower() not in ("0", "off", "false")

    def send(self, key, value):
        self.rpc("config_set", key, value)

    def send_int(self, key, ctrl):
        text = ctrl.GetValue().strip()
        if not text.lstrip("-").isdigit():
            self.say(self.tr("cfg.notnumber"))
            return
        self.send(key, text)

    def _show_value(self, key, value):
        self.values[key] = value
        row = self.controls.get(key)
        if not row:
            return
        opt, c = row["opt"], row["main"]
        kind = opt.get("type")
        if kind == "bool":
            c.SetValue(self._on(value))
        elif kind == "enum":
            if str(value) in row["keys"]:
                c.SetSelection(row["keys"].index(str(value)))
        elif kind in ("int", "string"):
            c.ChangeValue("" if value is None else str(value))
        elif kind == "account":
            token = value.get("token") if isinstance(value, dict) else None
            c.ChangeValue(("/link " + token) if token else "")
        status = self.describe(opt, value)
        row["status"].SetLabel(status)
        name = row["label"]
        if row.get("range"):
            name += ", " + row["range"]
        if status:
            name += ": " + status
        if kind == "account" and c.GetValue():
            name += ". " + self.tr("cfg.secret")
        row["acc"].name = name
        self.panel.Layout()

    def on_result(self, body):
        if not isinstance(body, dict) or not body.get("key"):
            return
        if body.get("ok"):
            self._show_value(body["key"], body.get("value"))
        else:
            self._show_value(body["key"], self.values.get(body["key"]))
            self.say(self.tr("cfg.refused", body.get("reason") or body.get("error") or ""))

    def on_changed(self, body):
        if isinstance(body, dict) and body.get("key"):
            self._show_value(body["key"], body.get("value"))


class AutoLoginDialog(wx.Dialog):
    """Saved characters for auto login. Passwords go to the Windows Credential
    Manager when OK is pressed; this dialog only collects the changes."""

    def __init__(self, parent, tr, enabled, chars, has_password):
        super().__init__(parent, title=tr("al2.title"), size=wx.Size(560, 460))
        self.tr, self.has_password = tr, has_password
        self.chars = list(chars)
        self.passwords = {}
        self.removed = set()
        s = wx.BoxSizer(wx.VERTICAL)
        self.enabled = wx.CheckBox(self, label=tr("al2.enabled"))
        self.enabled.SetValue(enabled)
        s.Add(self.enabled, 0, wx.ALL, 6)
        self.list = labelled(self, s, tr("al2.chars"), wx.ListBox(self), expand="grow")
        self.name = labelled(self, s, tr("al2.name"), wx.TextCtrl(self))
        self.password = labelled(self, s, tr("al2.password"), wx.TextCtrl(self, style=wx.TE_PASSWORD))
        row = wx.BoxSizer(wx.HORIZONTAL)
        add = wx.Button(self, label=tr("al2.add"))
        remove = wx.Button(self, label=tr("al2.remove"))
        row.Add(add, 0, wx.ALL, 4)
        row.Add(remove, 0, wx.ALL, 4)
        s.Add(row, 0, wx.ALL, 2)
        add.Bind(wx.EVT_BUTTON, self.on_add)
        remove.Bind(wx.EVT_BUTTON, self.on_remove)
        self.list.Bind(wx.EVT_LISTBOX, self.on_pick)
        self.name.Bind(wx.EVT_SET_FOCUS, self.on_name_focus)
        ok = ok_cancel(self, s, tr)
        ok.Bind(wx.EVT_BUTTON, self.on_ok)
        self.SetSizer(s)
        self.fill()
        self.enabled.SetFocus()

    def saved(self, name):
        if name.lower() in self.passwords:
            return True
        return name.lower() not in self.removed and self.has_password(name)

    def fill(self, keep=None):
        rows = [self.tr("al2.row", n) if self.saved(n) else self.tr("al2.rownopass", n) for n in self.chars]
        self.list.Set(rows or [self.tr("al2.none")])
        if self.chars:
            self.list.SetSelection(self.chars.index(keep) if keep in self.chars else 0)
        self.on_pick(None)

    def on_pick(self, event):
        i = self.list.GetSelection()
        self.name.SetValue(self.chars[i] if 0 <= i < len(self.chars) else "")
        self.password.SetValue("")

    def on_name_focus(self, event):
        event.Skip()
        wx.CallAfter(self.name.SelectAll)

    def on_add(self, event):
        name = self.name.GetValue().strip()
        if not name:
            message(self, self.tr("al2.needname"), self.tr("al2.title"))
            return self.name.SetFocus()
        name = name[:1].upper() + name[1:]
        existing = next((n for n in self.chars if n.lower() == name.lower()), None)
        if existing is None:
            self.chars.append(name)
            existing = name
        if self.password.GetValue():
            self.passwords[existing.lower()] = (existing, self.password.GetValue())
            self.removed.discard(existing.lower())
        self.password.SetValue("")
        self.fill(existing)
        self.list.SetFocus()

    def on_remove(self, event):
        i = self.list.GetSelection()
        if not 0 <= i < len(self.chars):
            return
        name = self.chars.pop(i)
        self.passwords.pop(name.lower(), None)
        self.removed.add(name.lower())
        self.fill()
        self.list.SetFocus()

    def on_ok(self, event):
        if self.enabled.GetValue() and not any(self.saved(n) for n in self.chars):
            message(self, self.tr("al2.needchar"), self.tr("al2.title"))
            return self.name.SetFocus()
        self.EndModal(wx.ID_OK)


class ChatDialog(wx.Dialog):
    def __init__(self, parent, tr, store, buffer_label):
        super().__init__(parent, title=tr("chat.title"), size=wx.Size(760, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr, self.store, self.buffer_label = tr, store, buffer_label
        s = wx.BoxSizer(wx.VERTICAL)
        self.buffers = list(store.order)
        self.choice = labelled(self, s, tr("chat.buffer"),
                               wx.Choice(self, choices=[buffer_label(b) for b in self.buffers]))
        self.choice.SetSelection(self.buffers.index(store.current) if store.current in self.buffers else 0)
        self.list = labelled(self, s, tr("chat.messages"), wx.ListBox(self), expand="grow")
        copy = wx.Button(self, label=tr("chat.copy"))
        close = wx.Button(self, wx.ID_CANCEL, tr("list.close"))
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(copy, 0, wx.ALL, 4)
        row.Add(close, 0, wx.ALL, 4)
        s.Add(row, 0, wx.ALL, 2)
        self.SetSizer(s)
        self.choice.Bind(wx.EVT_CHOICE, lambda e: self.fill())
        copy.Bind(wx.EVT_BUTTON, lambda e: self.copy())
        self.list.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self.fill()
        self.list.SetFocus()

    def fill(self):
        name = self.buffers[self.choice.GetSelection()]
        self.rows = self.store.buffer_rows(name)
        items = [self.describe(r) for r in self.rows] or [self.tr("chat.empty")]
        self.list.Set(items)
        self.list.SetSelection(len(items) - 1)

    def describe(self, r):
        when = time.strftime("%H:%M", time.localtime(r.get("at") or 0))
        return "%s, %s" % (r.get("text", ""), when)

    def copy(self):
        i = self.list.GetSelection()
        if 0 <= i < len(self.rows) and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.rows[i].get("text", "")))
            wx.TheClipboard.Close()
            wx.MessageBox(self.tr("chat.copied"), self.tr("chat.title"), wx.OK, self)

    def on_key(self, event):
        if event.ControlDown() and event.GetKeyCode() == ord("C"):
            return self.copy()
        event.Skip()


SOUND_TYPES = ["combat", "alert", "chat", "ui", "ambient", "music"]
SOUND_SAMPLE = {"combat": "combat/hit", "alert": "alert/bell", "chat": "chat/tell", "ui": "ui/notify"}


class SoundDialog(wx.Dialog):
    def __init__(self, parent, tr, prefs, player):
        super().__init__(parent, title=tr("snd.title"))
        self.prefs = prefs
        self.player = player
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(self, label=tr("snd.intro")), 0, wx.ALL, 6)
        self.on = wx.CheckBox(self, label=tr("snd.on"))
        self.on.SetValue(not prefs.get("mute"))
        self.on.Bind(wx.EVT_CHECKBOX, self.on_toggle)
        s.Add(self.on, 0, wx.ALL, 6)
        self.master = self._slider(s, tr("snd.master"), prefs.get("master", 80), None, tr)
        self.master.Bind(wx.EVT_SLIDER, lambda e: self._set_master())
        box = wx.StaticBoxSizer(wx.VERTICAL, self, tr("snd.types"))
        self.sliders = {}
        types = prefs.setdefault("types", {})
        for kind in SOUND_TYPES:
            sl = self._slider(box, tr("snd.type." + kind), types.get(kind, 100), kind, tr, parent=box.GetStaticBox())
            sl.Bind(wx.EVT_SLIDER, lambda e, k=kind: self._set_type(k))
            self.sliders[kind] = sl
        s.Add(box, 0, wx.EXPAND | wx.ALL, 6)
        ok = wx.Button(self, wx.ID_OK, tr("ok"))
        ok.SetDefault()
        s.Add(ok, 0, wx.ALL | wx.ALIGN_RIGHT, 6)
        self.SetEscapeId(wx.ID_OK)
        self.SetSizerAndFit(s)
        self.on.SetFocus()

    def _slider(self, sizer, label, value, kind, tr, parent=None):
        parent = parent or self
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        sl = wx.Slider(parent, value=int(value), minValue=0, maxValue=100, size=(220, -1))
        sl.SetName(label)
        sl._acc = NamedAccessible(sl, label)
        sl.SetPageSize(10)
        row.Add(sl, 1, wx.EXPAND | wx.ALL, 6)
        if kind in SOUND_SAMPLE:
            b = wx.Button(parent, label=tr("snd.play"))
            b._acc = NamedAccessible(b, tr("snd.play") + ": " + label)
            b.Bind(wx.EVT_BUTTON, lambda e, k=kind: self.player.try_sound(SOUND_SAMPLE[k], k))
            row.Add(b, 0, wx.ALL, 6)
        sizer.Add(row, 0, wx.EXPAND)
        return sl

    def on_toggle(self, event):
        self.prefs["mute"] = not self.on.GetValue()
        if self.prefs["mute"]:
            self.player.stop_all()

    def _set_master(self):
        self.prefs["master"] = self.master.GetValue()

    def _set_type(self, kind):
        self.prefs.setdefault("types", {})[kind] = self.sliders[kind].GetValue()


class SpeechFilterDialog(wx.Dialog):
    def __init__(self, parent, tr, words):
        super().__init__(parent, title=tr("sf.title"), size=(560, 400),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        s = wx.BoxSizer(wx.VERTICAL)
        self.text = labelled(self, s, tr("sf.label"), wx.TextCtrl(self, value="\n".join(words),
                                                                   style=wx.TE_MULTILINE), expand="grow")
        ok_cancel(self, s, tr)
        self.SetSizer(s)
        self.text.SetFocus()

    def words(self):
        return [w.strip() for w in self.text.GetValue().splitlines() if w.strip()]


class FindDialog(wx.Dialog):
    def __init__(self, parent, tr, value):
        super().__init__(parent, title=tr("find.title"))
        s = wx.BoxSizer(wx.VERTICAL)
        self.text = labelled(self, s, tr("find.label"), wx.TextCtrl(self, value=value, size=(360, -1)))
        ok_cancel(self, s, tr)
        self.SetSizerAndFit(s)
        self.text.SelectAll()
        self.text.SetFocus()


class HelpSearchDialog(wx.Dialog):
    def __init__(self, parent, tr, searcher, lang, say):
        super().__init__(parent, title=tr("hs.title"), size=wx.Size(720, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr, self.searcher, self.lang, self.say = tr, searcher, lang, say
        self.rows = []
        self.choice = None
        self.timer = None
        s = wx.BoxSizer(wx.VERTICAL)
        self.search = labelled(self, s, tr("hs.search"), wx.TextCtrl(self))
        self.status = wx.StaticText(self, label=tr("hs.type"))
        s.Add(self.status, 0, wx.LEFT | wx.RIGHT, 6)
        self.list = labelled(self, s, tr("hs.results"), wx.ListBox(self), expand="grow")
        row = wx.BoxSizer(wx.HORIZONTAL)
        read = wx.Button(self, wx.ID_OK, tr("hs.read"))
        close = wx.Button(self, wx.ID_CANCEL, tr("list.close"))
        read.SetDefault()
        row.Add(read, 0, wx.ALL, 4)
        row.Add(close, 0, wx.ALL, 4)
        s.Add(row, 0, wx.ALL, 2)
        self.SetSizer(s)
        self.search.Bind(wx.EVT_TEXT, self.on_text)
        self.search.Bind(wx.EVT_KEY_DOWN, self.on_search_key)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.done())
        read.Bind(wx.EVT_BUTTON, lambda e: self.done())
        self.search.SetFocus()

    def on_text(self, event):
        if self.timer:
            self.timer.Stop()
        self.timer = wx.CallLater(250, self.run)

    def run(self):
        query = self.search.GetValue().strip()
        if not query:
            self.rows = []
            self.list.Set([])
            self.status.SetLabel(self.tr("hs.type"))
            return
        try:
            found, suggested = self.searcher.search(query, self.lang)
        except Exception:
            self.status.SetLabel(self.tr("hs.offline"))
            return self.say(self.tr("hs.offline"))
        self.rows = found
        labels = []
        for r in found:
            text = r["title"] + (", " + r["kind"] if r["kind"] else "")
            if r["extra"]:
                text += ". " + r["extra"]
            labels.append(text)
        self.list.Set(labels)
        if found:
            self.list.SetSelection(0)
            note = self.tr("hs.suggest", len(found)) if suggested else self.tr("hs.count", len(found))
        else:
            note = self.tr("hs.none")
        self.status.SetLabel(note)
        self.say(note, False)

    def on_search_key(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_DOWN and self.rows:
            self.list.SetFocus()
            return
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if self.timer and self.timer.IsRunning():
                self.timer.Stop()
                self.run()
            return self.done()
        event.Skip()

    def done(self):
        i = self.list.GetSelection()
        if 0 <= i < len(self.rows):
            self.choice = self.rows[i]["id"]
            self.EndModal(wx.ID_OK)


class EditorDialog(wx.Dialog):
    def __init__(self, parent, tr, text):
        super().__init__(parent, title=tr("ed.title"), size=wx.Size(760, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(self, label=tr("ed.intro")), 0, wx.ALL, 6)
        self.text = labelled(self, s, tr("ed.text"), wx.TextCtrl(self, value=text.replace("\r", ""),
                                                                 style=wx.TE_MULTILINE | wx.TE_RICH2), expand="grow")
        row = wx.BoxSizer(wx.HORIZONTAL)
        save = wx.Button(self, wx.ID_OK, tr("ed.save"))
        cancel = wx.Button(self, wx.ID_CANCEL, tr("cancel"))
        row.Add(save, 0, wx.ALL, 4)
        row.Add(cancel, 0, wx.ALL, 4)
        s.Add(row, 0, wx.ALL | wx.ALIGN_RIGHT, 2)
        self.SetSizer(s)
        ident = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, lambda e: self.EndModal(wx.ID_OK), id=ident)
        self.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_CTRL, ord("S"), ident),
                                                     (wx.ACCEL_CTRL, wx.WXK_RETURN, ident)]))
        self.text.SetFocus()
        self.text.SetInsertionPoint(0)

    def value(self):
        text = self.text.GetValue().replace("\r\n", "\n").replace("\r", "\n")
        return text if text.endswith("\n") or not text else text + "\n"


class ScriptEditDialog(wx.Dialog):
    def __init__(self, parent, tr, text, source):
        super().__init__(parent, title=tr("se.title"), size=wx.Size(800, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(self, label=tr("se.intro") + " " + tr("se.source." + (source or "none"))), 0, wx.ALL, 6)
        self.text = labelled(self, s, tr("se.text"), wx.TextCtrl(self, value=text,
                                                                 style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.HSCROLL),
                             expand="grow")
        self.text.SetFont(wx.Font(wx.FontInfo(11).Family(wx.FONTFAMILY_TELETYPE)))
        row = wx.BoxSizer(wx.HORIZONTAL)
        save = wx.Button(self, wx.ID_OK, tr("se.save"))
        cancel = wx.Button(self, wx.ID_CANCEL, tr("cancel"))
        row.Add(save, 0, wx.ALL, 4)
        row.Add(cancel, 0, wx.ALL, 4)
        s.Add(row, 0, wx.ALL | wx.ALIGN_RIGHT, 2)
        self.SetSizer(s)
        ident = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, lambda e: self.EndModal(wx.ID_OK), id=ident)
        self.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_CTRL, ord("S"), ident)]))
        self.text.SetFocus()

    def value(self):
        return self.text.GetValue().replace("\r\n", "\n")


class AccountDialog(wx.Dialog):
    SWITCH, PROFILE = 301, 302

    def __init__(self, parent, tr, data):
        super().__init__(parent, title=tr("acc.title"), size=wx.Size(560, 440),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr = tr
        self.chars = [c for c in data.get("chars") or [] if isinstance(c, dict) and c.get("name")]
        self.choice = None
        s = wx.BoxSizer(wx.VERTICAL)
        head = tr("acc.current", data.get("current") or "")
        if data.get("title"):
            head += " " + str(data["title"])
        s.Add(wx.StaticText(self, label=head), 0, wx.ALL, 6)
        self.list = labelled(self, s, tr("acc.list"), wx.ListBox(self, choices=[self.label(c) for c in self.chars]
                                                                or [tr("acc.none")]), expand="grow")
        if self.chars:
            self.list.SetSelection(0)
        row = wx.BoxSizer(wx.HORIZONTAL)
        switch = wx.Button(self, self.SWITCH, tr("acc.switch"))
        profile = wx.Button(self, self.PROFILE, tr("acc.profile"))
        close = wx.Button(self, wx.ID_CANCEL, tr("list.close"))
        switch.SetDefault()
        for b in (switch, profile, close):
            row.Add(b, 0, wx.ALL, 4)
        s.Add(row, 0, wx.ALL, 2)
        self.SetSizer(s)
        switch.Bind(wx.EVT_BUTTON, lambda e: self.done(self.SWITCH))
        profile.Bind(wx.EVT_BUTTON, lambda e: self.done(self.PROFILE))
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.done(self.SWITCH))
        self.list.SetFocus()

    def label(self, c):
        lang = self.tr.lang
        parts = [c["name"]]
        if c.get("level"):
            parts.append(self.tr("acc.level", c["level"]))
        cls = c.get("class")
        if isinstance(cls, dict):
            cls = cls.get(lang) or cls.get("en") or cls.get("ru")
        if cls:
            parts.append(str(cls))
        prof = c.get("profile") or {}
        if prof.get("hidden"):
            parts.append(self.tr("acc.hidden"))
        return ", ".join(parts)

    def done(self, how):
        i = self.list.GetSelection()
        if 0 <= i < len(self.chars):
            self.choice = (self.chars[i], how)
            self.EndModal(wx.ID_OK)


class AutobuffLineEdit(wx.Dialog):
    def __init__(self, parent, tr, gate="*", cmd=""):
        super().__init__(parent, title=tr("ab.line"))
        s = wx.BoxSizer(wx.VERTICAL)
        self.gate = labelled(self, s, tr("ab.gate"), wx.TextCtrl(self, value=gate, size=wx.Size(360, -1)))
        self.gate.SetMaxLength(40)
        self.cmd = labelled(self, s, tr("ab.cmd"), wx.TextCtrl(self, value=cmd, size=wx.Size(360, -1)))
        self.cmd.SetMaxLength(200)
        ok_cancel(self, s, tr)
        self.SetSizerAndFit(s)
        self.cmd.SetFocus()


class AutobuffDialog(wx.Dialog):
    MAX_LINES = 20

    def __init__(self, parent, tr, send, say):
        super().__init__(parent, title=tr("ab.title"), size=wx.Size(640, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr, self.send, self.say = tr, send, say
        self.spells, self.custom = [], []
        self.seq = 0
        s = wx.BoxSizer(wx.VERTICAL)
        self.info = wx.StaticText(self, label=tr("ab.loading"))
        s.Add(self.info, 0, wx.ALL, 6)
        self.list = labelled(self, s, tr("ab.spells"), wx.CheckListBox(self), expand="grow")
        r1 = wx.BoxSizer(wx.HORIZONTAL)
        up = wx.Button(self, label=tr("ab.up"))
        down = wx.Button(self, label=tr("ab.down"))
        r1.Add(up, 0, wx.ALL, 4)
        r1.Add(down, 0, wx.ALL, 4)
        s.Add(r1, 0)
        self.lines = labelled(self, s, tr("ab.own"), wx.ListBox(self), expand="grow")
        r2 = wx.BoxSizer(wx.HORIZONTAL)
        add = wx.Button(self, label=tr("list.add"))
        edit = wx.Button(self, label=tr("ab.edit"))
        remove = wx.Button(self, label=tr("ab.remove"))
        close = wx.Button(self, wx.ID_CANCEL, tr("list.close"))
        for b in (add, edit, remove, close):
            r2.Add(b, 0, wx.ALL, 4)
        s.Add(r2, 0)
        self.SetSizer(s)
        self.list.Bind(wx.EVT_CHECKLISTBOX, self.on_check)
        up.Bind(wx.EVT_BUTTON, lambda e: self.move(-1))
        down.Bind(wx.EVT_BUTTON, lambda e: self.move(1))
        add.Bind(wx.EVT_BUTTON, lambda e: self.edit_line(None))
        edit.Bind(wx.EVT_BUTTON, lambda e: self.edit_line(self.lines.GetSelection()))
        remove.Bind(wx.EVT_BUTTON, lambda e: self.remove_line())
        self.lines.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.edit_line(self.lines.GetSelection()))
        self.list.SetFocus()
        self.request()

    def next_seq(self):
        self.seq += 1
        return str(self.seq)

    def request(self):
        if not self.send("autobuff_prefs", "list", self.next_seq()):
            self.info.SetLabel(self.tr("cfg.wait"))

    def on_data(self, data):
        if str(data.get("seq")) != str(self.seq):
            return
        self.spells = [dict(x) for x in data.get("spells") or [] if isinstance(x, dict) and x.get("sn")]
        self.custom = [dict(x) for x in data.get("custom") or [] if isinstance(x, dict)]
        self.fill()
        self.info.SetLabel(self.tr("ab.intro") if self.spells or self.custom else self.tr("ab.empty"))

    def fill(self, keep=None, keep_line=None):
        sel = self.list.GetSelection() if keep is None else keep
        self.list.Set([x.get("name") or x["sn"] for x in self.spells])
        for i, x in enumerate(self.spells):
            self.list.Check(i, bool(x.get("on")))
        if self.spells:
            self.list.SetSelection(max(0, min(sel if sel != wx.NOT_FOUND else 0, len(self.spells) - 1)))
        lsel = self.lines.GetSelection() if keep_line is None else keep_line
        self.lines.Set([self.line_label(x) for x in self.custom])
        if self.custom:
            self.lines.SetSelection(max(0, min(lsel if lsel != wx.NOT_FOUND else 0, len(self.custom) - 1)))

    def line_label(self, x):
        gate = x.get("gate") or "*"
        head = self.tr("ab.always") if gate == "*" else self.tr("ab.unless", gate)
        text = "%s: %s" % (head, x.get("cmd") or "")
        if x.get("bad"):
            text += " " + self.tr("ab.bad")
        return text

    def commit(self):
        order = ",".join(x["sn"] for x in self.spells)
        off = ",".join(x["sn"] for x in self.spells if not x.get("on"))
        clean = lambda v: " ".join(str(v or "").split())
        own = "\n".join("%s\t%s" % (clean(x.get("gate")) or "*", clean(x.get("cmd"))) for x in self.custom)
        self.send("autobuff_prefs", "set", order, off, own, self.next_seq())

    def on_check(self, event):
        i = event.GetInt()
        if 0 <= i < len(self.spells):
            self.spells[i]["on"] = 1 if self.list.IsChecked(i) else 0
            self.commit()

    def move(self, step):
        i = self.list.GetSelection()
        j = i + step
        if i == wx.NOT_FOUND or not (0 <= j < len(self.spells)):
            return
        self.spells[i], self.spells[j] = self.spells[j], self.spells[i]
        self.fill(keep=j)
        self.list.SetFocus()
        self.say(self.tr("ab.moved", self.spells[j].get("name") or self.spells[j]["sn"], j + 1))
        self.commit()

    def edit_line(self, i):
        new = i is None or i == wx.NOT_FOUND
        if new and len(self.custom) >= self.MAX_LINES:
            return self.say(self.tr("list.full"))
        x = {} if new else self.custom[i]
        dlg = AutobuffLineEdit(self, self.tr, x.get("gate") or "*", x.get("cmd") or "")
        if dlg.ShowModal() == wx.ID_OK and dlg.cmd.GetValue().strip():
            row = {"gate": dlg.gate.GetValue().strip() or "*", "cmd": dlg.cmd.GetValue().strip()}
            if new:
                self.custom.append(row)
                i = len(self.custom) - 1
            else:
                self.custom[i] = row
            self.fill(keep_line=i)
            self.commit()
        dlg.Destroy()
        self.lines.SetFocus()

    def remove_line(self):
        i = self.lines.GetSelection()
        if 0 <= i < len(self.custom):
            del self.custom[i]
            self.fill(keep_line=i)
            self.commit()
            self.lines.SetFocus()


class UpdateDialog(wx.Dialog):
    def __init__(self, parent, tr, new, old, notes):
        super().__init__(parent, title=tr("upd.title"), size=wx.Size(620, 480),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        s = wx.BoxSizer(wx.VERTICAL)
        head = wx.StaticText(self, label=tr("upd.head", new, old))
        s.Add(head, 0, wx.ALL, 8)
        self.notes = labelled(self, s, tr("upd.notes"), wx.TextCtrl(
            self, value=notes.replace("\r\n", "\n").replace("\n", "\r\n"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2), expand="grow")
        row = wx.BoxSizer(wx.HORIZONTAL)
        yes = wx.Button(self, wx.ID_YES, tr("upd.yes"))
        no = wx.Button(self, wx.ID_NO, tr("upd.no"))
        yes.SetDefault()
        row.Add(yes, 0, wx.ALL, 4)
        row.Add(no, 0, wx.ALL, 4)
        s.Add(row, 0, wx.ALL, 4)
        self.SetSizer(s)
        yes.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_YES))
        no.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_NO))
        self.SetEscapeId(wx.ID_NO)
        self.notes.SetFocus()
        self.notes.SetInsertionPoint(0)


class ItemsDialog(wx.Dialog):
    KEYS = {
        "item": {(wx.WXK_DELETE, False): ["drop"], (wx.WXK_DELETE, True): ["drop", "sacrifice"],
                 (ord("C"), True): ["compare"], (ord("L"), True): ["look"], (ord("W"), True): ["wear"],
                 (ord("R"), True): ["remove"], (ord("G"), True): ["get"], (ord("N"), True): ["open"]},
        "mob": {(ord("L"), True): ["look"], (ord("C"), True): ["consider"], (ord("K"), True): ["kill"],
                (ord("F"), True): ["follow"]},
        "player": {(ord("L"), True): ["look"], (ord("H"), True): ["whois"], (ord("F"), True): ["follow"],
                   (ord("T"), True): ["tell"]},
    }

    def __init__(self, parent, tr, title, rows, act, keys_text=None):
        super().__init__(parent, title=title, size=wx.Size(640, 500),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr, self.rows, self.act = tr, rows, act
        self.choice = None
        s = wx.BoxSizer(wx.VERTICAL)
        self.keys_label = wx.StaticText(self, label=keys_text or tr("items.keys"))
        s.Add(self.keys_label, 0, wx.ALL, 6)
        self.list = labelled(self, s, title, wx.ListBox(self, choices=[r["label"] for r in rows] or [tr("items.none")]),
                             expand="grow")
        if rows:
            self.list.SetSelection(0)
        row = wx.BoxSizer(wx.HORIZONTAL)
        actions = wx.Button(self, wx.ID_OK, tr("items.actions").replace("&", ""))
        close = wx.Button(self, wx.ID_CANCEL, tr("list.close").replace("&", ""))
        actions.SetDefault()
        row.Add(actions, 0, wx.ALL, 4)
        row.Add(close, 0, wx.ALL, 4)
        s.Add(row, 0, wx.ALL, 2)
        self.SetSizer(s)
        actions.Bind(wx.EVT_BUTTON, lambda e: self.menu())
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.menu())
        self.list.Bind(wx.EVT_KEY_DOWN, self.on_key)
        accel = []
        combos = set()
        for table in self.KEYS.values():
            combos.update(table)
        combos.update({(ord(c), True) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"})
        for key, alt in combos:
            ident = wx.NewIdRef()
            self.Bind(wx.EVT_MENU, lambda e, k=key, a=alt: self.shortcut(k, a), id=ident)
            accel.append((wx.ACCEL_ALT if alt else wx.ACCEL_NORMAL, key, ident))
        self.SetAcceleratorTable(wx.AcceleratorTable(accel))
        self.list.SetFocus()

    def shortcut(self, key, alt):
        row = self.current()
        if not row:
            return
        if row.get("keys") is not None:
            cmds = row["keys"].get((key, alt))
            if cmds:
                return self.pick(("commands", cmds, row))
        else:
            verbs = self.KEYS.get(row["kind"], {}).get((key, alt))
            if verbs:
                return self.pick(("verbs", verbs, row))
        if alt:
            cmd = self.dynamic(row).get(chr(key).upper())
            if cmd:
                self.pick(("command", cmd, row))

    def fixed_letters(self, row):
        table = row["keys"] if row.get("keys") is not None else self.KEYS.get(row["kind"], {})
        return {chr(k).upper() for (k, alt) in table if alt and 32 < k < 128}

    def dynamic(self, row):
        if "_dyn" in row:
            return row["_dyn"]
        taken = self.fixed_letters(row)
        out = {}
        for entry in row.get("menu") or []:
            if entry is None:
                continue
            label, cmd = entry
            for ch in label.upper():
                if "A" <= ch <= "Z" and ch not in taken:
                    taken.add(ch)
                    out[ch] = cmd
                    break
        row["_dyn"] = out
        return out

    def current(self):
        i = self.list.GetSelection()
        return self.rows[i] if 0 <= i < len(self.rows) else None

    def on_key(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not event.HasAnyModifiers():
            return self.menu()
        row = self.current()
        if row and row.get("keys") is not None:
            return event.Skip()
        if row:
            verbs = self.KEYS.get(row["kind"], {}).get((key, event.AltDown()))
            if verbs and not event.ControlDown() and not event.ShiftDown():
                return self.pick(("verbs", verbs, row))
        event.Skip()

    def menu(self):
        row = self.current()
        if not row:
            return
        menu = wx.Menu()
        keys = {cmd: letter for letter, cmd in self.dynamic(row).items()}
        for entry in row["menu"]:
            if entry is None:
                menu.AppendSeparator()
                continue
            text, cmd = entry
            if cmd in keys:
                text = "%s (Alt+%s)" % (text, keys[cmd])
            it = menu.Append(wx.ID_ANY, text)
            self.Bind(wx.EVT_MENU, lambda e, c=cmd: self.pick(("command", c, row)), it)
        self.PopupMenu(menu)
        menu.Destroy()

    def pick(self, choice):
        self.choice = choice
        self.act(choice)

    def set_rows(self, title, rows, keys_text=None):
        if keys_text:
            self.keys_label.SetLabel(keys_text)
        keep = self.list.GetSelection()
        self.rows = rows
        self.SetTitle(title)
        self.list.Set([r["label"] for r in rows] or [self.tr("items.none")])
        if rows:
            self.list.SetSelection(max(0, min(keep if keep != wx.NOT_FOUND else 0, len(rows) - 1)))
        self.list.SetFocus()
