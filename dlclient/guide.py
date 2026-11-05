"""The game guide window: zone quests, items, class skills, gods and races,
read from the website data that sitedata keeps up to date.

The row and detail text builders are plain functions so tests can check them
without a window.
"""
import wx

from . import sitedata as SD
from .dialogs import labelled

ALIGNS = ("", "good", "neutral", "evil")


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
            parts.append(it["wclass"])
        ave = SD.num(it.get("ave"))
        if ave:
            parts.append(tr("guide.ave", ave))
    elif it.get("wearloc"):
        parts.append(it["wearloc"])
    stats = SD.stat_text(it)
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


def skill_row(tr, level, skills, mine):
    key = "guide.s.done" if mine and level <= mine else "guide.s.row"
    return tr(key, level, ", ".join(skills))


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

    def __init__(self, book, tr, title):
        super().__init__(book)
        self.tr = tr
        self.rows = []
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.search = labelled(self, self.sizer, tr("guide.search"), wx.TextCtrl(self))
        self.extra = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.extra, 0, wx.EXPAND)
        self.list = labelled(self, self.sizer, tr("guide.list"), wx.ListBox(self), expand="grow")
        self.detail = labelled(self, self.sizer, tr("guide.details"), wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=wx.Size(-1, 140)), expand="grow")
        self.SetSizer(self.sizer)
        self.search.Bind(wx.EVT_TEXT, lambda e: self.refill())
        self.search.Bind(wx.EVT_KEY_DOWN, self.on_search_key)
        self.list.Bind(wx.EVT_LISTBOX, lambda e: self.show())
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.detail.SetFocus())
        book.AddPage(self, title)

    def on_search_key(self, event):
        if event.GetKeyCode() == wx.WXK_DOWN and self.rows:
            self.list.SetFocus()
            return
        event.Skip()

    def build(self):
        """Override: list of (label, detail, search text)."""
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
        self.level = wx.SpinCtrl(self, min=1, max=100, initial=int(ctx.get("level") or 1))
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
        self.level.Bind(wx.EVT_SPINCTRL, lambda e: self.context_changed())
        self.level.Bind(wx.EVT_TEXT, lambda e: self.context_changed())
        self.cls.Bind(wx.EVT_CHOICE, lambda e: self.context_changed())
        self.align.Bind(wx.EVT_CHOICE, lambda e: self.context_changed())
        for p in self.pages:
            p.refill()
        self.book.SetSelection(0)
        self.pages[0].search.SetFocus()

    # Character -----------------------------------------------------------
    def context(self):
        i = self.cls.GetSelection()
        j = self.align.GetSelection()
        return {"level": self.level.GetValue(),
                "class": self.classes[i - 1] if 1 <= i <= len(self.classes) else "",
                "align": ALIGNS[j] if 0 <= j < len(ALIGNS) else ""}

    def set_context(self, ctx, notify=True):
        if ctx.get("level"):
            self.level.SetValue(int(ctx["level"]))
        cls = (ctx.get("class") or "").lower()
        names = [c.lower() for c in self.classes]
        self.cls.SetSelection(names.index(cls) + 1 if cls in names else 0)
        self.align.SetSelection(ALIGNS.index(ctx["align"]) if ctx.get("align") in ALIGNS else 0)
        if notify:
            self.context_changed()

    def context_changed(self):
        ctx = self.context()
        if self.on_ctx:
            self.on_ctx(ctx)
        if getattr(self, "pages", None):
            self.items.low.SetValue(max(1, ctx["level"] - 5))
            self.items.high.SetValue(ctx["level"])
            for p in self.pages:
                p.refill(p.list.GetSelection() if p is not self.skills else self.skill_start())

    # Pages ---------------------------------------------------------------
    def quests_page(self):
        tr, site = self.tr, self.site
        page = Page(self.book, tr, tr("guide.tab.quests"))
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
                out.append((quest_row(tr, q), quest_detail(tr, site, q), q["zone"] + " " + q["text"]))
            return out
        page.build = build
        return page

    def items_page(self):
        tr, site = self.tr, self.site
        page = Page(self.book, tr, tr("guide.tab.items"))
        lvl = self.level.GetValue()
        page.kind = wx.Choice(page, choices=[tr("guide.weapons"), tr("guide.armor")])
        page.kind.SetSelection(0)
        page.slot = wx.Choice(page)
        page.low = wx.SpinCtrl(page, min=1, max=100, initial=max(1, lvl - 5))
        page.high = wx.SpinCtrl(page, min=1, max=100, initial=lvl)
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
            page.slot.Set([tr("guide.anyslot")] + page.slot_values[1:])
            page.slot.SetSelection(0)

        def build():
            k = kind()
            i = page.slot.GetSelection()
            slot = page.slot_values[i] if 0 < i < len(page.slot_values) else None
            found = site.items(k, page.low.GetValue(), page.high.GetValue(), self.context()["align"] or None,
                               slot=slot if k == "armor" else None, wclass=slot if k == "weapon" else None)
            return [(item_row(tr, site, it, k), item_detail(tr, site, it, k),
                     item_row(tr, site, it, k) + " " + " ".join(site.item_place(it))) for it in found]
        slots()
        page.kind.Bind(wx.EVT_CHOICE, lambda e: (slots(), page.refill()))
        page.slot.Bind(wx.EVT_CHOICE, lambda e: page.refill())
        for ctrl in (page.low, page.high):
            ctrl.Bind(wx.EVT_SPINCTRL, lambda e: page.refill())
            ctrl.Bind(wx.EVT_TEXT, lambda e: page.refill())
        page.build = build
        self.items = page
        return page

    def skills_page(self):
        tr, site = self.tr, self.site
        page = Page(self.book, tr, tr("guide.tab.skills"))

        def build():
            ctx = self.context()
            if not ctx["class"]:
                return [(tr("guide.pickclass"), tr("guide.pickclass"), "")]
            out = []
            for level, skills in site.class_skills(ctx["class"]):
                text = skill_row(tr, level, skills, ctx["level"])
                out.append((text, text, text))
            return out
        page.build = build
        self.skills = page
        page.refill = lambda select=None, _r=page.refill: _r(self.skill_start() if select is None else select)
        return page

    def skill_start(self):
        """The first skill level the character has not reached yet."""
        ctx = self.context()
        rows = self.site.class_skills(ctx["class"]) if ctx["class"] else []
        return next((i for i, (lv, _s) in enumerate(rows) if lv > ctx["level"]), 0)

    def info_page(self, key, records, fields):
        site = self.site
        page = Page(self.book, self.tr, self.tr("guide.tab." + key))

        def build():
            return [(r["name"], info_detail(site, r, fields),
                     " ".join([r["name"]] + [r.get(f, "") for f in fields])) for r in records]
        page.build = build
        return page
