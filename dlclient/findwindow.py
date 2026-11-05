"""One window for finding things: rooms, areas, the guide's quests, items,
skills, gods and races, and item search.

A FindWindow shows one or more views (several as tabs). Each view is a list.
Typing anywhere in the window goes to the search box above the list and
narrows it; Down goes back to the list, Up from its first row back to the box.
Enter opens the selected row's details. The buttons beside the list act on the
selected row (walk there, show the route, read the help). Ctrl+1 to Ctrl+9
each open one of the view's filters in a small window of its own; the Filters
button lists them all, and a line above the list says which are set.

The window does no game actions itself: an action closes it with
(view key, action key, payload) in `result`, and the caller walks, sends or
shows what it means.
"""
import wx

from .access import NamedAccessible


def _name(ctrl, label):
    label = label.replace("&", "")
    ctrl.SetName(label)
    ctrl._acc = NamedAccessible(ctrl, label)
    return ctrl


class Row:
    __slots__ = ("label", "search", "payload")

    def __init__(self, label, payload=None, search=None):
        self.label = label
        self.payload = payload
        self.search = (search if search is not None else label).lower()


class Filter:
    """One filter. kind is 'choice' (choices: [(value, label)]), 'number',
    'range' (value is (low, high)) or 'check'. get() and set(value) read and
    store the value; set() is where the caller saves it."""

    def __init__(self, key, label, kind, get, set, choices=None, low=1, high=100, describe=None):
        self.key, self.label, self.kind = key, label, kind
        self.get, self.set = get, set
        self.choices = choices
        self.low, self.high = low, high
        self._describe = describe

    def options(self):
        return self.choices() if callable(self.choices) else (self.choices or [])

    def describe(self, tr):
        """The value in words, for the line of active filters."""
        if self._describe:
            return self._describe(self.get())
        v = self.get()
        if self.kind == "choice":
            return next((label for value, label in self.options() if value == v), str(v))
        if self.kind == "range":
            return "%s - %s" % v
        if self.kind == "check":
            return tr("find.yes") if v else tr("find.no")
        return str(v)


class Action:
    """A button beside the list. can(payload) says whether it applies to a row;
    when it does not, pressing it says so instead of doing nothing. value(payload)
    is what the window hands back (the payload itself unless given)."""

    def __init__(self, key, label, can=None, value=None):
        self.key, self.label = key, label
        self.can = can or (lambda payload: True)
        self.value = value or (lambda payload: payload)


class View:
    """rows(): the full list as Rows, filters applied, search not. detail(payload):
    the text Enter shows. Filters keep their Ctrl numbers in list order."""

    def __init__(self, key, title, rows, detail, actions=(), filters=(), empty=None):
        self.key, self.title = key, title
        self.rows, self.detail = rows, detail
        self.actions, self.filters = list(actions), list(filters)
        self.empty = empty


class NumberBox(wx.TextCtrl):
    """A number in a plain edit box: Up and Down change it by one, Page Up and
    Page Down by ten."""

    def __init__(self, parent, value, low, high):
        super().__init__(parent, value=str(value), style=wx.TE_PROCESS_ENTER)
        self.low, self.high = low, high
        self.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def number(self):
        text = self.GetValue().strip()
        n = int(text) if text.isdigit() else self.low
        return min(max(n, self.low), self.high)

    def on_key(self, event):
        step = {wx.WXK_UP: 1, wx.WXK_DOWN: -1, wx.WXK_PAGEUP: 10, wx.WXK_PAGEDOWN: -10}.get(event.GetKeyCode())
        if not step:
            return event.Skip()
        self.SetValue(str(min(max(self.number() + step, self.low), self.high)))
        self.SetInsertionPointEnd()


class FilterDialog(wx.Dialog):
    """One filter in a window of its own. Enter applies, Escape cancels."""

    def __init__(self, parent, tr, flt):
        super().__init__(parent, title=flt.label.replace("&", ""))
        self.flt = flt
        s = wx.BoxSizer(wx.VERTICAL)
        v = flt.get()
        self.ctrls = []
        if flt.kind == "choice":
            opts = flt.options()
            c = wx.Choice(self, choices=[label for _v, label in opts])
            values = [value for value, _l in opts]
            c.SetSelection(values.index(v) if v in values else 0)
            self._read = lambda: values[c.GetSelection()] if 0 <= c.GetSelection() < len(values) else v
            self._add(s, flt.label, c)
        elif flt.kind == "range":
            low = NumberBox(self, v[0], flt.low, flt.high)
            high = NumberBox(self, v[1], flt.low, flt.high)
            self._add(s, tr("find.from"), low)
            self._add(s, tr("find.to"), high)
            self._read = lambda: (min(low.number(), high.number()), max(low.number(), high.number()))
        elif flt.kind == "number":
            n = NumberBox(self, v, flt.low, flt.high)
            self._add(s, flt.label, n)
            self._read = n.number
        else:
            c = wx.CheckBox(self, label=flt.label)
            c.SetValue(bool(v))
            s.Add(c, 0, wx.ALL, 8)
            self.ctrls.append(c)
            self._read = c.GetValue
        row = wx.StdDialogButtonSizer()
        ok = wx.Button(self, wx.ID_OK, tr("find.ok"))
        cancel = wx.Button(self, wx.ID_CANCEL, tr("find.cancel"))
        ok.SetDefault()
        row.AddButton(ok)
        row.AddButton(cancel)
        row.Realize()
        s.Add(row, 0, wx.ALL | wx.ALIGN_RIGHT, 6)
        self.SetSizerAndFit(s)
        for c in self.ctrls:
            if isinstance(c, wx.TextCtrl):
                c.Bind(wx.EVT_TEXT_ENTER, lambda e: self.EndModal(wx.ID_OK))
        if self.ctrls:
            self.ctrls[0].SetFocus()
            if isinstance(self.ctrls[0], wx.TextCtrl):
                self.ctrls[0].SelectAll()

    def _add(self, sizer, label, ctrl):
        sizer.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        sizer.Add(_name(ctrl, label), 0, wx.EXPAND | wx.ALL, 8)
        self.ctrls.append(ctrl)

    def value(self):
        return self._read()


class DetailsDialog(wx.Dialog):
    def __init__(self, parent, tr, title, text):
        super().__init__(parent, title=title, size=wx.Size(640, 460), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        t = _name(wx.TextCtrl(self, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2), title)
        close = wx.Button(self, wx.ID_CANCEL, tr("find.close"))
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(t, 1, wx.EXPAND | wx.ALL, 6)
        s.Add(close, 0, wx.ALL | wx.ALIGN_RIGHT, 6)
        self.SetSizer(s)
        t.SetFocus()


class ViewPanel(wx.Panel):
    """One view: search box, the line of filters, the list and its buttons."""

    def __init__(self, parent, window, view):
        super().__init__(parent)
        self.window, self.view, self.tr = window, view, window.tr
        self.shown = []
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(self, label=self.tr("find.search")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
        self.search = _name(wx.TextCtrl(self), self.tr("find.search"))
        s.Add(self.search, 0, wx.EXPAND | wx.ALL, 6)
        self.filters_line = wx.StaticText(self, label="")
        s.Add(self.filters_line, 0, wx.LEFT | wx.RIGHT, 8)
        s.Add(wx.StaticText(self, label=view.title), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
        body = wx.BoxSizer(wx.HORIZONTAL)
        self.list = _name(wx.ListBox(self), view.title)
        body.Add(self.list, 1, wx.EXPAND | wx.ALL, 6)
        buttons = wx.BoxSizer(wx.VERTICAL)
        self.buttons = []
        details = wx.Button(self, label=self.tr("find.details"))
        details.Bind(wx.EVT_BUTTON, lambda e: self.show_details())
        buttons.Add(details, 0, wx.EXPAND | wx.ALL, 3)
        for act in view.actions:
            b = wx.Button(self, label=act.label)
            b.Bind(wx.EVT_BUTTON, lambda e, a=act: self.run(a))
            buttons.Add(b, 0, wx.EXPAND | wx.ALL, 3)
            self.buttons.append(b)
        if view.filters:
            fb = wx.Button(self, label=self.tr("find.filters"))
            fb.Bind(wx.EVT_BUTTON, lambda e: self.window.list_filters())
            buttons.Add(fb, 0, wx.EXPAND | wx.ALL, 3)
        body.Add(buttons, 0, wx.ALL, 3)
        s.Add(body, 1, wx.EXPAND)
        self.SetSizer(s)
        self.search.Bind(wx.EVT_TEXT, lambda e: self.refill())
        self.search.Bind(wx.EVT_KEY_DOWN, self.on_search_key)
        self.list.Bind(wx.EVT_KEY_DOWN, self.on_list_key)
        self.list.Bind(wx.EVT_CHAR, self.on_list_char)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.show_details())

    # ---- the list ----------------------------------------------------------
    def refill(self, keep=None):
        """keep: the payload to stay on, else the row at the same place."""
        old = self.selected()
        index = self.list.GetSelection()
        words = self.search.GetValue().strip().lower().split()
        rows = self.view.rows()
        if words:
            rows = [r for r in rows if all(w in r.search for w in words)]
        self.shown = rows
        self.list.Set([r.label for r in rows] or [self.view.empty or self.tr("find.none")])
        target = keep if keep is not None else (old.payload if old else None)
        pos = next((i for i, r in enumerate(rows) if target is not None and r.payload is target), None)
        if pos is None:
            pos = min(max(index, 0), max(len(rows) - 1, 0))
        self.list.SetSelection(pos)
        self.update_filters_line()

    def selected(self):
        i = self.list.GetSelection()
        return self.shown[i] if 0 <= i < len(self.shown) else None

    def update_filters_line(self):
        parts = ["%s: %s" % (f.label.replace("&", ""), f.describe(self.tr)) for f in self.view.filters]
        self.filters_line.SetLabel(self.tr("find.active", "; ".join(parts)) if parts else "")

    # ---- keys --------------------------------------------------------------
    def on_search_key(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_DOWN, wx.WXK_PAGEDOWN) and self.shown:
            self.list.SetFocus()
            return
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            return self.show_details()
        event.Skip()

    def on_list_key(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            return self.show_details()
        if key == wx.WXK_UP and self.list.GetSelection() <= 0:
            self.search.SetFocus()
            self.search.SetInsertionPointEnd()
            return
        if key == wx.WXK_BACK:
            self.search.SetFocus()
            text = self.search.GetValue()
            self.search.SetValue(text[:-1])
            self.search.SetInsertionPointEnd()
            return
        event.Skip()

    def on_list_char(self, event):
        # Typed letters, Cyrillic too, go to the search box. Not skipped: the
        # list's own type-to-select would jump the selection.
        ch = event.GetUnicodeKey()
        if ch >= 32 and not event.ControlDown() and not event.AltDown():
            self.search.SetFocus()
            self.search.AppendText(chr(ch))
            self.search.SetInsertionPointEnd()
            return
        event.Skip()

    # ---- actions -----------------------------------------------------------
    def show_details(self):
        row = self.selected()
        if not row:
            return self.window.say(self.view.empty or self.tr("find.none"))
        dlg = DetailsDialog(self, self.tr, row.label.split(",")[0], self.view.detail(row.payload))
        dlg.ShowModal()
        dlg.Destroy()
        self.list.SetFocus()

    def run(self, act):
        row = self.selected()
        if not row:
            return self.window.say(self.view.empty or self.tr("find.none"))
        if not act.can(row.payload):
            return self.window.say(self.tr("find.cannot"))
        self.window.finish(self.view.key, act.key, act.value(row.payload))


class FindWindow(wx.Dialog):
    """views: one or more View. say(text) speaks a short message. With several
    views they are tabs; tab_keys maps a letter to a view for Alt+Shift+letter."""

    def __init__(self, parent, tr, title, views, say=None, tab_keys=None, size=(820, 640)):
        super().__init__(parent, title=title, size=wx.Size(*size), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr, self.say_cb = tr, say
        self.result = None
        s = wx.BoxSizer(wx.VERTICAL)
        if len(views) > 1:
            self.book = wx.Notebook(self)
            self.panels = []
            for v in views:
                p = ViewPanel(self.book, self, v)
                self.book.AddPage(p, v.title)
                self.panels.append(p)
            s.Add(self.book, 1, wx.EXPAND | wx.ALL, 4)
            self.book.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, lambda e: (e.Skip(), self.panel().refill()))
        else:
            self.book = None
            self.panels = [ViewPanel(self, self, views[0])]
            s.Add(self.panels[0], 1, wx.EXPAND | wx.ALL, 4)
        close = wx.Button(self, wx.ID_CANCEL, tr("find.close"))
        s.Add(close, 0, wx.ALL | wx.ALIGN_RIGHT, 4)
        self.SetSizer(s)
        accel = []
        for n in range(1, 10):
            ident = wx.NewIdRef()
            self.Bind(wx.EVT_MENU, lambda e, n=n: self.open_filter(n - 1), id=ident)
            accel.append((wx.ACCEL_CTRL, ord(str(n)), ident))
        for letter, key in (tab_keys or {}).items():
            ident = wx.NewIdRef()
            self.Bind(wx.EVT_MENU, lambda e, k=key: self.select_view(k), id=ident)
            accel.append((wx.ACCEL_ALT | wx.ACCEL_SHIFT, ord(letter), ident))
        self.SetAcceleratorTable(wx.AcceleratorTable(accel))
        for p in self.panels:
            p.refill()
        self.panels[0].list.SetFocus()

    def say(self, text):
        if self.say_cb:
            self.say_cb(text)

    def panel(self):
        return self.panels[self.book.GetSelection()] if self.book else self.panels[0]

    def select_view(self, key):
        for i, p in enumerate(self.panels):
            if p.view.key == key:
                if self.book:
                    self.book.SetSelection(i)
                p.refill()
                p.list.SetFocus()
                return True
        return False

    def refill_all(self):
        for p in self.panels:
            p.refill()

    # ---- filters -----------------------------------------------------------
    def open_filter(self, index):
        p = self.panel()
        if not 0 <= index < len(p.view.filters):
            return self.say(self.tr("find.nofilter", index + 1))
        flt = p.view.filters[index]
        dlg = FilterDialog(self, self.tr, flt)
        if dlg.ShowModal() == wx.ID_OK:
            flt.set(dlg.value())
            # Filters can be shared by the views (the guide's character): all refill.
            self.refill_all()
            self.say(self.tr("find.count", "%s: %s" % (flt.label.replace("&", ""), flt.describe(self.tr)), len(p.shown)))
        dlg.Destroy()
        p.list.SetFocus()

    def list_filters(self):
        """The Filters button: every filter with its Ctrl number, Enter opens one."""
        p = self.panel()
        labels = ["Ctrl+%d, %s: %s" % (i + 1, f.label.replace("&", ""), f.describe(self.tr))
                  for i, f in enumerate(p.view.filters)]
        dlg = wx.SingleChoiceDialog(self, self.tr("find.filterlist"), self.tr("find.filters").replace("&", ""), labels)
        if dlg.ShowModal() == wx.ID_OK:
            i = dlg.GetSelection()
            dlg.Destroy()
            return self.open_filter(i)
        dlg.Destroy()
        p.list.SetFocus()

    # ---- closing -----------------------------------------------------------
    def finish(self, view_key, action_key, payload):
        self.result = (view_key, action_key, payload)
        if self.IsModal():
            self.EndModal(wx.ID_OK)

    def show_again(self, view_key=None):
        """Open a kept window as it was left: same view, search, filters and row."""
        self.result = None
        if view_key:
            self.select_view(view_key)
        p = self.panel()
        wx.CallAfter(p.list.SetFocus)
        return self.ShowModal()
