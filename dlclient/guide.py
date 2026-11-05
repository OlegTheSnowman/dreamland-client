"""The game guide window: zone quests, items, class skills, gods and races,
read from the website data that sitedata keeps up to date.

The row and detail text builders are plain functions so tests can check them
without a window.
"""
import wx

from . import sitedata as SD
from .dialogs import labelled

ALIGNS = ("", "good", "neutral", "evil")


class NumberField(wx.TextCtrl):
    """A plain edit box for a level: screen readers read its label, Up and Down change it."""

    def __init__(self, parent, value, low=1, high=100):
        super().__init__(parent, value=str(value))
        self.low, self.high = low, high
        self.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def number(self):
        text = self.GetValue().strip()
        n = int(text) if text.isdigit() else self.low
        return min(max(n, self.low), self.high)

    def set_number(self, n):
        self.ChangeValue(str(min(max(int(n), self.low), self.high)))

    def on_key(self, event):
        step = {wx.WXK_UP: 1, wx.WXK_DOWN: -1, wx.WXK_PAGEUP: 10, wx.WXK_PAGEDOWN: -10}.get(event.GetKeyCode())
        if not step:
            return event.Skip()
        n = min(max(self.number() + step, self.low), self.high)
        self.SetValue(str(n))
        self.SetInsertionPointEnd()


def levels_text(tr, low, high):
    if low and high:
        return tr("guide.levels", low, high)
    if low:
        return tr("guide.levelfrom", low)
    return ""


def quest_row(tr, q):
    parts = [q["zone"] + ": " + q["text"]]
    lv = levels_text(tr, q["low"], q["high"])
    if lv:
        parts.append(lv)
    if q["align"]:
        parts.append(q["align"])
    if q["often"]:
        parts.append(q["often"])
    return ", ".join(parts)


def quest_detail(tr, site, q):
    L = site.L
    lines = [q["text"]]
    lv = levels_text(tr, q["low"], q["high"])
    if lv:
        lines.append(lv)
    for label, key in ((L["align"], "align"), (L["often"], "often"), (L["requires"], "requires")):
        if q[key]:
            lines.append("%s: %s" % (label, q[key]))
    lines.append("")
    lines.append(q["zone"])
    for label, key in ((L["levels"], "levels"), (L["danger"], "danger"), (L["route"], "route")):
        if q[key]:
            lines.append("%s: %s" % (label, q[key]))
    return "\n".join(lines)


def quest_fits(q, level, align):
    if level and q["low"] and level < q["low"]:
        return False
    if level and q["high"] and level > q["high"]:
        return False
    return SD.align_ok(q["align"], align)


def item_row(tr, site, it, kind):
    parts = [site.item_name(it), tr("guide.lvl", SD.num(it.get("level")) or 0)]
    if kind == "weapon":
        if it.get("wclass"):
            parts.append(SD.word(tr, "guide.wc.", it["wclass"]))
        ave = SD.num(it.get("ave"))
        if ave:
            parts.append(tr("guide.ave", ave))
    elif it.get("wearloc"):
        parts.append(SD.word(tr, "guide.wear.", it["wearloc"]))
    stats = SD.stat_text(it, tr)
    if stats:
        parts.append(stats)
    area, where = site.item_place(it)
    if area:
        parts.append(area)
    return ", ".join(parts)


def item_detail(tr, site, it, kind):
    lines = [item_row(tr, site, it, kind)]
    d1, d2 = SD.num(it.get("d1")), SD.num(it.get("d2"))
    if kind == "weapon" and d1 and d2:
        lines.append(tr("guide.dice", d1, d2))
    area, where = site.item_place(it)
    if area or where:
        lines.append(tr("guide.where", area, where) if where else area)
    if (it.get("align") or "").strip() not in ("", "-"):
        lines.append(tr("guide.only", ", ".join(tr("guide.align." + a) for a in ALIGNS[1:]
                                                if SD.usable_by(it["align"], a))))
    if (SD.num(it.get("limit")) or 0) > 0:
        lines.append(tr("guide.limited", SD.num(it["limit"])))
    if site.lang == "ru" and str(it.get("special") or "").strip("- "):
        lines.append(str(it["special"]))
    lines.append(tr("guide.vnum", it.get("vnum", "")))
    return "\n".join(lines)


def skill_row(tr, sk, teacher, mine):
    key = "guide.s.done" if mine and sk["level"] <= mine else "guide.s.row"
    text = tr(key, sk["level"], sk["name"])
    if teacher.get("group"):
        text += ", " + teacher["group"]
    if teacher.get("teacher"):
        text += ". " + teacher["teacher"]
    return text


def info_detail(site, rec, fields):
    lines = [rec["name"]]
    for key in fields:
        if rec.get(key):
            lines.append("%s: %s" % (site.L[key], rec[key]))
    body = site.article_text(rec["id"])
    if body:
        lines += ["", body]
    return "\n".join(lines)


class Page(wx.Panel):
    """A search field, a list and a read-only details box."""

    def __init__(self, book, tr, title, go=None):
        super().__init__(book)
        self.tr, self.go = tr, go
        self.rows = []
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.search = labelled(self, self.sizer, tr("guide.search"), wx.TextCtrl(self))
        self.extra = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.extra, 0, wx.EXPAND)
        self.list = labelled(self, self.sizer, tr("guide.list"), wx.ListBox(self), expand="grow")
        self.detail = labelled(self, self.sizer, tr("guide.details"), wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=wx.Size(-1, 140)), expand="grow")
        if go:
            button = wx.Button(self, label=tr("guide.go"))
            self.sizer.Add(button, 0, wx.ALL, 4)
            button.Bind(wx.EVT_BUTTON, lambda e: self.go_selected())
        self.SetSizer(self.sizer)
        self.search.Bind(wx.EVT_TEXT, lambda e: self.refill())
        self.search.Bind(wx.EVT_KEY_DOWN, self.on_search_key)
        self.list.Bind(wx.EVT_LISTBOX, lambda e: self.show())
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.go_selected() if go else self.detail.SetFocus())
        self.list.Bind(wx.EVT_KEY_DOWN, self.on_list_key)
        book.AddPage(self, title)

    def on_search_key(self, event):
        if event.GetKeyCode() == wx.WXK_DOWN and self.rows:
            self.list.SetFocus()
            return
        event.Skip()

    def on_list_key(self, event):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            return self.go_selected() if self.go else self.detail.SetFocus()
        event.Skip()

    def go_selected(self):
        i = self.list.GetSelection()
        if self.go and 0 <= i < len(self.rows) and len(self.rows[i]) > 3 and self.rows[i][3]:
            self.go(self.rows[i][3])

    def build(self):
        """Override: list of (label, detail, search text[, place names to walk to])."""
        return []

    def refill(self, select=0):
        q = self.search.GetValue().strip().lower()
        rows = self.build()
        if q:
            rows = [r for r in rows if all(w in r[2].lower() for w in q.split())]
        self.rows = rows
        self.list.Set([r[0] for r in rows] or [self.tr("guide.none")])
        self.list.SetSelection(min(max(select, 0), max(len(rows) - 1, 0)))
        self.show()

    def show(self):
        i = self.list.GetSelection()
        self.detail.SetValue(self.rows[i][1] if 0 <= i < len(self.rows) else "")


class GuideDialog(wx.Dialog):
    def __init__(self, parent, tr, site, ctx, on_ctx=None):
        super().__init__(parent, title=tr("guide.title"), size=wx.Size(760, 640),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.tr, self.site, self.on_ctx = tr, site, on_ctx
        self.classes = site.class_names()
        s = wx.BoxSizer(wx.VERTICAL)
        top = wx.BoxSizer(wx.HORIZONTAL)
        self.choice = None
        self.level = NumberField(self, int(ctx.get("level") or 1))
        self.cls = wx.Choice(self, choices=[tr("guide.anyclass")] + self.classes)
        self.align = wx.Choice(self, choices=[tr("guide.align." + (a or "any")) for a in ALIGNS])
        for label, ctrl in ((tr("guide.level"), self.level), (tr("guide.class"), self.cls),
                            (tr("guide.align"), self.align)):
            box = wx.BoxSizer(wx.VERTICAL)
            labelled(self, box, label, ctrl)
            top.Add(box, 1, wx.ALL, 2)
        s.Add(top, 0, wx.EXPAND)
        self.set_context(ctx, notify=False)
        self.book = wx.Notebook(self)
        s.Add(self.book, 1, wx.EXPAND | wx.ALL, 4)
        self.pages = [self.quests_page(), self.items_page(), self.skills_page(),
                      self.info_page("gods", site.religions(), ("paths", "patron", "gifts", "restrict")),
                      self.info_page("races", site.races(), ("align", "stats", "classes", "resist", "vuln", "size"))]
        close = wx.Button(self, wx.ID_CANCEL, tr("list.close"))
        s.Add(close, 0, wx.ALL, 4)
        self.SetSizer(s)
        self.level.Bind(wx.EVT_TEXT, lambda e: self.context_changed())
        self.cls.Bind(wx.EVT_CHOICE, lambda e: self.context_changed())
        self.align.Bind(wx.EVT_CHOICE, lambda e: self.context_changed())
        for p in self.pages:
            p.refill()
        self.book.SetSelection(0)
        self.last_focus = self.pages[0].search
        self.Bind(wx.EVT_CHILD_FOCUS, self.on_child_focus)
        self.pages[0].search.SetFocus()

    def on_child_focus(self, event):
        win = event.GetWindow()
        if win and win is not self:
            self.last_focus = win
        event.Skip()

    def show_again(self):
        """Open the kept window where it was left: same tab, filters and focus."""
        self.choice = None
        target = self.last_focus
        if target:
            wx.CallAfter(lambda: target and target.SetFocus())
        return self.ShowModal()

    # Character -----------------------------------------------------------
    def context(self):
        i = self.cls.GetSelection()
        j = self.align.GetSelection()
        return {"level": self.level.number(),
                "class": self.classes[i - 1] if 1 <= i <= len(self.classes) else "",
                "align": ALIGNS[j] if 0 <= j < len(ALIGNS) else ""}

    def set_context(self, ctx, notify=True):
        before = self.context()
        if ctx.get("level"):
            self.level.set_number(ctx["level"])
        cls = (ctx.get("class") or "").lower()
        names = [c.lower() for c in self.classes]
        self.cls.SetSelection(names.index(cls) + 1 if cls in names else 0)
        self.align.SetSelection(ALIGNS.index(ctx["align"]) if ctx.get("align") in ALIGNS else 0)
        if notify and self.context() != before:
            self.context_changed()

    def context_changed(self):
        ctx = self.context()
        if self.on_ctx:
            self.on_ctx(ctx)
        if getattr(self, "pages", None):
            if ctx["level"] != self.items.level:
                self.items.level = ctx["level"]
                self.items.low.set_number(max(1, ctx["level"] - 5))
                self.items.high.set_number(ctx["level"])
            for p in self.pages:
                p.refill(p.list.GetSelection() if p is not self.skills else self.skill_start())

    def go(self, names):
        """Close the guide and let the main window walk to this zone."""
        self.choice = list(names)
        if self.IsModal():
            self.EndModal(wx.ID_OK)

    def zone_names(self, q):
        return self.site.zone_names(q["zone_id"]) or [q["zone"]]

    # Pages ---------------------------------------------------------------
    def quests_page(self):
        tr, site = self.tr, self.site
        page = Page(self.book, tr, tr("guide.tab.quests"), self.go)
        page.fits = wx.CheckBox(page, label=tr("guide.mylevel"))
        page.fits.SetValue(True)
        page.extra.Add(page.fits, 0, wx.ALL, 4)
        page.fits.Bind(wx.EVT_CHECKBOX, lambda e: page.refill())
        quests = site.zone_quests()

        def build():
            ctx = self.context()
            out = []
            for q in sorted(quests, key=lambda q: (q["low"], q["zone"].lower())):
                if page.fits.GetValue() and not quest_fits(q, ctx["level"], ctx["align"]):
                    continue
                out.append((quest_row(tr, q), quest_detail(tr, site, q), q["zone"] + " " + q["text"],
                            self.zone_names(q)))
            return out
        page.build = build
        return page

    def items_page(self):
        tr, site = self.tr, self.site
        page = Page(self.book, tr, tr("guide.tab.items"), self.go)
        lvl = self.level.number()
        page.level = lvl
        page.kind = wx.Choice(page, choices=[tr("guide.weapons"), tr("guide.armor")])
        page.kind.SetSelection(0)
        page.slot = wx.Choice(page)
        page.low = NumberField(page, max(1, lvl - 5))
        page.high = NumberField(page, lvl)
        row = wx.BoxSizer(wx.HORIZONTAL)
        for label, ctrl in ((tr("guide.kind"), page.kind), (tr("guide.slot"), page.slot),
                            (tr("guide.from"), page.low), (tr("guide.to"), page.high)):
            box = wx.BoxSizer(wx.VERTICAL)
            labelled(page, box, label, ctrl)
            row.Add(box, 1, wx.ALL, 2)
        page.extra.Add(row, 0, wx.EXPAND)

        def kind():
            return "weapon" if page.kind.GetSelection() == 0 else "armor"

        def slots():
            page.slot_values = [""] + site.slots(kind())
            prefix = "guide.wc." if kind() == "weapon" else "guide.wear."
            page.slot.Set([tr("guide.anyslot")] + [SD.word(tr, prefix, v) for v in page.slot_values[1:]])
            page.slot.SetSelection(0)

        def build():
            k = kind()
            i = page.slot.GetSelection()
            slot = page.slot_values[i] if 0 < i < len(page.slot_values) else None
            found = site.items(k, page.low.number(), page.high.number(), self.context()["align"] or None,
                               slot=slot if k == "armor" else None, wclass=slot if k == "weapon" else None)
            return [(item_row(tr, site, it, k), item_detail(tr, site, it, k),
                     item_row(tr, site, it, k) + " " + " ".join(site.item_place(it)),
                     [n for n in (site.item_place(it)[0], it.get("areaEn"), it.get("area")) if n]) for it in found]
        slots()
        page.kind.Bind(wx.EVT_CHOICE, lambda e: (slots(), page.refill()))
        page.slot.Bind(wx.EVT_CHOICE, lambda e: page.refill())
        for ctrl in (page.low, page.high):
            ctrl.Bind(wx.EVT_TEXT, lambda e: page.refill())
        page.build = build
        self.items = page
        return page

    def skills_page(self):
        tr, site = self.tr, self.site
        page = Page(self.book, tr, tr("guide.tab.skills"), self.go)

        def build():
            ctx = self.context()
            if not ctx["class"]:
                return [(tr("guide.pickclass"), tr("guide.pickclass"), "")]
            teachers = site.skill_teachers()
            out = []
            for sk in site.class_skill_list(ctx["class"]):
                t = teachers.get(sk["id"]) or {}
                text = skill_row(tr, sk, t, ctx["level"])
                detail = text
                body = site.article_text(sk["id"]) if sk["id"] else ""
                if body:
                    detail += "\n\n" + body
                out.append((text, detail, text, site.zone_names(t["zone_id"]) if t.get("zone_id") else None))
            return out
        page.build = build
        self.skills = page
        page.refill = lambda select=None, _r=page.refill: _r(self.skill_start() if select is None else select)
        return page

    def skill_start(self):
        """The first skill level the character has not reached yet."""
        ctx = self.context()
        rows = self.site.class_skill_list(ctx["class"]) if ctx["class"] else []
        return next((i for i, sk in enumerate(rows) if sk["level"] > ctx["level"]), 0)

    def info_page(self, key, records, fields):
        site = self.site
        page = Page(self.book, self.tr, self.tr("guide.tab." + key))

        def build():
            return [(r["name"], info_detail(site, r, fields),
                     " ".join([r["name"]] + [r.get(f, "") for f in fields])) for r in records]
        page.build = build
        return page
