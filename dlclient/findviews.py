"""The views shown in a FindWindow: rooms, areas, the guide's tabs and item
search. Each builder returns View objects; the caller acts on the result."""
from . import sitedata as SD
from .findwindow import Action, Filter, Row, View
from .guide import (ALIGNS, HORSE_SLOTS, info_detail, item_detail, item_row, quest_detail, quest_fits,
                    quest_row, skill_row)

# ---- rooms ---------------------------------------------------------------------


def room_label(tr, r):
    steps = r.get("steps")
    if steps == 0:
        return "%s, %s" % (r["name"], tr("map.here"))
    if steps:
        return "%s, %s" % (r["name"], tr("map.step1") if steps == 1 else tr("map.steps", steps))
    return r["name"]


def room_detail(tr, r):
    lines = [room_label(tr, r)]
    if r.get("exits"):
        lines.append(tr("find.exits", ", ".join(tr("dir." + d) for d in r["exits"])))
    if r.get("desc"):
        lines += ["", r["desc"]]
    return "\n".join(lines)


def rooms_view(tr, rooms):
    """rooms: [{vnum, name, steps, desc, exits}] of the area the player is in."""
    rows = [Row(room_label(tr, r), r, r["name"]) for r in rooms]
    return View("rooms", tr("rooms.list"), lambda: rows, lambda r: room_detail(tr, r),
                actions=[Action("walk", tr("rooms.walk")), Action("route", tr("rooms.route"))],
                empty=tr("rooms.none"))


# ---- areas ---------------------------------------------------------------------

AREA_SORTS = ("name", "level", "levelhigh", "near")


def area_label(tr, a):
    text = tr("areas.row", a["name"], a["min"], a["max"]) if a["levels"] and a["max"] else a["name"]
    if a.get("danger"):
        text += ", " + tr("areas.danger." + a["danger"])
    if a.get("steps"):
        text += ", " + tr("areas.steps", a["steps"])
    return text


def area_detail(tr, a):
    lines = [area_label(tr, a)]
    if a.get("route"):
        lines.append(tr("areas.route", a["route"]))
    else:
        lines.append(tr("areas.noroute"))
    if a.get("note"):
        lines.append(tr("areas.then", a["note"]))
    return "\n".join(lines)


def areas_view(tr, areas, opts, save):
    """opts: {"sort", "levels": (low, high) or None}; save(opts) keeps them."""
    state = {"sort": opts.get("sort") if opts.get("sort") in AREA_SORTS else "name",
             "levels": tuple(opts["levels"]) if opts.get("levels") else (1, 100)}

    def rows():
        low, high = state["levels"]
        shown = [a for a in areas if (low, high) == (1, 100) or
                 (a["levels"] and a["max"] and a["min"] >= low and a["max"] <= high)]
        order = state["sort"]
        if order == "level":
            shown.sort(key=lambda a: (not a["levels"], a["min"], a["max"], a["name"].lower()))
        elif order == "levelhigh":
            shown.sort(key=lambda a: (not a["levels"], -a["min"], -a["max"], a["name"].lower()))
        elif order == "near":
            shown.sort(key=lambda a: (a.get("steps") is None, a.get("steps") or 0, a["name"].lower()))
        else:
            shown.sort(key=lambda a: a["name"].lower())
        return [Row(area_label(tr, a), a, " ".join((a["name"], a["en"], a["ru"]))) for a in shown]

    def setter(key):
        def set_(value):
            state[key] = value
            save(dict(state))
        return set_

    filters = [
        Filter("levels", tr("find.f.levels"), "range", lambda: state["levels"], setter("levels")),
        Filter("sort", tr("areas.sort"), "choice", lambda: state["sort"], setter("sort"),
               choices=[("name", tr("areas.byname")), ("level", tr("areas.bylevel")),
                        ("levelhigh", tr("areas.bylevelhigh")), ("near", tr("areas.bynear"))]),
    ]
    has_route = lambda a: bool(a.get("route"))
    return View("areas", tr("areas.list"), rows, lambda a: area_detail(tr, a),
                actions=[Action("walk", tr("rooms.walk"), has_route), Action("route", tr("rooms.route"), has_route),
                         Action("help", tr("areas.help"))],
                filters=filters, empty=tr("rooms.none"))


# ---- the guide -----------------------------------------------------------------


def item_place_names(site, it):
    return [n for n in (site.item_place(it)[0], it.get("areaEn"), it.get("area")) if n]


def guide_views(tr, site, ctx, opts, save_ctx, save_opts):
    """The guide's five views. ctx {level, class, align} is shared: its filters
    have the same Ctrl numbers (1 to 3) on every tab. save_ctx(ctx) and
    save_opts(opts) keep the values between sessions."""
    classes = site.class_names()
    ctx = {"level": int(ctx.get("level") or 1), "class": ctx.get("class") or "", "align": ctx.get("align") or ""}
    if ctx["class"].lower() not in [c.lower() for c in classes]:
        ctx["class"] = ""
    else:
        ctx["class"] = next(c for c in classes if c.lower() == ctx["class"].lower())
    opts = dict(opts or {})

    def set_ctx(key):
        def set_(value):
            ctx[key] = value
            save_ctx(dict(ctx))
        return set_

    def set_opt(key):
        def set_(value):
            opts[key] = value
            save_opts(dict(opts))
        return set_

    character = [
        Filter("level", tr("guide.level"), "number", lambda: ctx["level"], set_ctx("level")),
        Filter("class", tr("guide.class"), "choice", lambda: ctx["class"], set_ctx("class"),
               choices=[("", tr("guide.anyclass"))] + [(c, c) for c in classes]),
        Filter("align", tr("guide.align"), "choice", lambda: ctx["align"], set_ctx("align"),
               choices=[(a, tr("guide.align." + (a or "any"))) for a in ALIGNS]),
    ]

    # Quests
    quests = sorted(site.zone_quests(), key=lambda q: (q["low"], q["zone"].lower()))

    def quest_rows():
        fits = opts.get("fits", True)
        return [Row(quest_row(tr, q), q, q["zone"] + " " + q["text"]) for q in quests
                if not fits or quest_fits(q, ctx["level"], ctx["align"])]

    zone_names = lambda q: site.zone_names(q["zone_id"]) or [q["zone"]]
    quests_v = View("quests", tr("guide.tab.quests"), quest_rows, lambda q: quest_detail(tr, site, q),
                    actions=[Action("go", tr("guide.go"), value=zone_names)],
                    filters=character + [Filter("fits", tr("guide.mylevel"), "check",
                                                lambda: bool(opts.get("fits", True)), set_opt("fits"))])

    # Items
    def kind():
        return "armor" if opts.get("kind") == "armor" else "weapon"

    def slot_choices():
        prefix = "guide.wc." if kind() == "weapon" else "guide.wear."
        out = [("", tr("guide.anyslot"))]
        if kind() == "weapon":
            out.append(("mine", tr("guide.mineweapons")))
        return out + [(v, SD.word(tr, prefix, v)) for v in site.slots(kind())]

    def get_slot():
        v = opts.get("slot_" + kind(), "")
        return v if v in [c for c, _l in slot_choices()] else ""

    def set_slot(value):
        opts["slot_" + kind()] = value
        save_opts(dict(opts))

    stat_choices = [("", tr("guide.anystat")), ("overall", tr("guide.overall"))] + \
        [(k, tr("guide.stat." + label)) for k, label in SD.STATS]

    def item_levels():
        # Stored as [low, high], high None meaning "my level", so the range
        # follows the character as it levels up unless set apart from it.
        v = opts.get("levels") or [1, None]
        low, high = v[0], v[1] if len(v) > 1 else None
        return (low, high or max(1, ctx["level"]))

    def item_rows():
        k, slot = kind(), get_slot()
        low, high = item_levels()
        mine = slot == "mine"
        found = site.items(k, low, high, ctx["align"] or None, slot=slot if k == "armor" and slot else None,
                           wclass=slot if k == "weapon" and slot and not mine else None)
        if k == "armor" and not slot:
            found = [it for it in found if it.get("wearloc") not in HORSE_SLOTS]
        if mine:
            allowed = set(site.class_weapons(ctx["class"])) if ctx["class"] else set()
            found = [it for it in found if it.get("wclass") in allowed]
        stat = opts.get("stat", "")
        if stat == "overall":
            found = sorted((it for it in found if SD.overall_score(it) > 0),
                           key=lambda it: (-SD.overall_score(it), -(SD.num(it.get("level")) or 0)))
        elif stat:
            found = sorted((it for it in found if SD.stat_gain(it, stat) > 0),
                           key=lambda it: (-SD.stat_gain(it, stat), -(SD.num(it.get("level")) or 0)))
        if opts.get("nominus"):
            found = [it for it in found if not SD.has_minus(it)]
        out = []
        for it in found:
            label = item_row(tr, site, it, k)
            out.append(Row(label, it, label + " " + " ".join(site.item_place(it))))
        return out

    def set_levels(value):
        low, high = value
        opts["levels"] = [low, None if high == ctx["level"] else high]
        save_opts(dict(opts))

    item_kind = lambda it: "weapon" if it.get("wclass") else "armor"
    items_v = View("items", tr("guide.tab.items"), item_rows, lambda it: item_detail(tr, site, it, item_kind(it)),
                   actions=[Action("go", tr("guide.go"), lambda it: bool(item_place_names(site, it)),
                                   lambda it: item_place_names(site, it))],
                   filters=character + [
                       Filter("kind", tr("guide.kind"), "choice", kind, set_opt("kind"),
                              choices=[("weapon", tr("guide.weapons")), ("armor", tr("guide.armor"))]),
                       Filter("slot", tr("guide.slot"), "choice", get_slot, set_slot, choices=slot_choices),
                       Filter("levels", tr("find.f.levels"), "range", item_levels, set_levels),
                       Filter("stat", tr("guide.stat"), "choice", lambda: opts.get("stat", ""), set_opt("stat"),
                              choices=stat_choices),
                       Filter("nominus", tr("guide.nominus"), "check", lambda: bool(opts.get("nominus")),
                              set_opt("nominus")),
                   ])

    # Skills
    def skill_rows():
        if not ctx["class"]:
            return []
        teachers = site.skill_teachers()
        out = []
        for sk in site.class_skill_list(ctx["class"]):
            t = teachers.get(sk["id"]) or {}
            out.append(Row(skill_row(tr, sk, t, ctx["level"]), (sk, t)))
        return out

    def skill_detail(p):
        sk, t = p
        text = skill_row(tr, sk, t, ctx["level"])
        body = site.article_text(sk["id"]) if sk["id"] else ""
        return text + ("\n\n" + body if body else "")

    skills_v = View("skills", tr("guide.tab.skills"), skill_rows, skill_detail,
                    actions=[Action("go", tr("guide.goteacher"), lambda p: bool(p[1].get("zone_id")),
                                    lambda p: site.zone_names(p[1]["zone_id"]))],
                    filters=character, empty=tr("guide.pickclass"))

    def info_view(key, records, fields):
        rows = [Row(r["name"], r) for r in records]
        return View(key, tr("guide.tab." + key), lambda: rows, lambda r: info_detail(site, r, fields),
                    filters=character)

    views = [quests_v, items_v, skills_v,
             info_view("gods", site.religions(), ("paths", "patron", "gifts", "restrict")),
             info_view("races", site.races(), ("align", "stats", "classes", "resist", "vuln", "size"))]

    def update_ctx(new):
        """The server's word on level and class (account_chars), into the open guide."""
        if new.get("level"):
            ctx["level"] = int(new["level"])
        cls = (new.get("class") or "").lower()
        ctx["class"] = next((c for c in classes if c.lower() == cls), ctx["class"])
        if new.get("align") in ALIGNS:
            ctx["align"] = new["align"]
    return views, update_ctx


# ---- item search ---------------------------------------------------------------


def item_search_view(tr, site):
    """Every weapon and armor, found by name in any language as the player types.
    No level or alignment limit: looked up by name, an item must not be hidden."""
    all_items = [("weapon", it) for it in site.weapons] + [("armor", it) for it in site.armor]
    rows = [Row(item_row(tr, site, it, k), it,
                " ".join(str(it.get(f) or "") for f in ("nameEn", "name", "nameUa")))
            for k, it in sorted(all_items, key=lambda p: (site.item_name(p[1]).lower(), -(SD.num(p[1].get("level")) or 0)))]
    item_kind = lambda it: "weapon" if it.get("wclass") else "armor"
    return View("lookup", tr("lookup.title"), lambda: rows, lambda it: item_detail(tr, site, it, item_kind(it)),
                actions=[Action("go", tr("guide.go"), lambda it: bool(item_place_names(site, it)),
                                lambda it: item_place_names(site, it))],
                empty=tr("lookup.none"))
