"""Text for the game guide: zone quests, items, class skills, gods and races,
read from the website data that sitedata keeps up to date. The guide's views
(findviews.py) show it in a FindWindow; these are plain functions so tests can
check them without a window.
"""
from . import sitedata as SD

ALIGNS = ("", "good", "neutral", "evil")
HORSE_SLOTS = ("horse", "hooves", "feet hooves")
# Tab order in the guide, and the letter that opens each one with Alt+Shift.
TABS = (("quests", "Q"), ("items", "I"), ("skills", "S"), ("gods", "G"), ("races", "R"))


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
    elif kind != "weapon":
        parts.append(tr("guide.nobonus"))
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
    levels, danger = site.zone_info(area) if hasattr(site, "zone_info") else ("", "")
    if levels or danger:
        lines.append(tr("guide.zone", ", ".join(x for x in (levels, danger) if x)))
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
