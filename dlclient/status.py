import re

COLOUR = re.compile(r"\{.")
AFFECT_ORDER = ("mal", "pro", "det", "trv", "enh", "cln", "cd")
STATS = ("str", "int", "wis", "dex", "con", "cha")
EXIT_LETTERS = (("n", "north"), ("e", "east"), ("s", "south"), ("w", "west"), ("u", "up"), ("d", "down"))


def clean(value):
    return COLOUR.sub("", str(value if value is not None else "")).strip()


def sentence(parts):
    parts = [x.rstrip(" .") for x in parts if x and x.strip(" .")]
    return ". ".join(parts) + "." if parts else ""


def present(value):
    return value not in (None, "", "none", [], {})


def hours(tr, d):
    if d is None:
        return ""
    if d < 0:
        return tr("st.perm")
    if d == 0:
        return tr("st.soon")
    unit, tens = d % 10, d % 100
    if tr.lang == "en":
        return "%d %s" % (d, tr("st.h1" if d == 1 else "st.h5"))
    if unit == 1 and tens != 11:
        return "%d %s" % (d, tr("st.h1"))
    if 2 <= unit <= 4 and not 12 <= tens <= 14:
        return "%d %s" % (d, tr("st.h2"))
    return "%d %s" % (d, tr("st.h5"))


def affects(p, tr):
    items = []
    for key in AFFECT_ORDER:
        block = p.get(key)
        if not isinstance(block, list):
            continue
        for aff in block:
            if isinstance(aff, dict) and aff.get("n"):
                items.append((key, aff))

    def rank(item):
        key, aff = item
        d = aff.get("d")
        return (key != "mal", float("inf") if d is None or d < 0 else d)
    items.sort(key=rank)
    if not items:
        return tr("st.noaff")
    out = []
    for key, aff in items:
        name = clean(aff.get("f") or aff.get("n"))
        bits = [name]
        if key == "mal":
            bits.append(tr("st.malad"))
        if key == "cd":
            bits.append(tr("st.cooldown"))
        left = hours(tr, aff.get("d"))
        if left:
            bits.append(left)
        out.append(", ".join(bits))
    return tr("st.affects", "; ".join(out))


def quests(p, tr):
    out = []
    q = p.get("q")
    if present(q) and isinstance(q, dict):
        out.append(tr("st.questor", clean(q.get("i")), clean(q.get("t"))))
    aq = p.get("aq")
    if present(aq) and isinstance(aq, dict):
        out.append("%s: %s" % (clean(aq.get("t")), clean(aq.get("i"))))
    return " ".join(out) if out else tr("st.noquest")


def group(p, tr):
    g = p.get("group")
    if not present(g) or not isinstance(g, dict):
        return tr("st.nogroup")
    rows = []
    for m in ([g.get("leader")] if g.get("leader") else []) + list(g.get("pc") or []) + list(g.get("npc") or []):
        if not isinstance(m, dict):
            continue
        text = tr("st.member", clean(m.get("sees")), m.get("level", ""), m.get("health", ""))
        if m.get("tnl") not in (None, ""):
            text += ", " + tr("st.tnl", m.get("tnl"))
        rows.append(text)
    if not rows:
        return tr("st.nogroup")
    return tr("st.group", clean(g.get("ln"))) + " " + "; ".join(rows)


def stats(p, tr):
    out = []
    p1 = p.get("p1")
    if present(p1) and isinstance(p1, dict):
        perm, cur = p1.get("ps") or [], p1.get("cs") or []
        parts = []
        for i, key in enumerate(STATS):
            if i < len(cur):
                value = str(cur[i])
                if i < len(perm) and perm[i] != cur[i]:
                    value += " (%s)" % perm[i]
                parts.append("%s %s" % (tr("st." + key), value))
        out.append(", ".join(parts))
    p2 = p.get("p2")
    if present(p2) and isinstance(p2, dict):
        out.append(tr("st.combat", p2.get("h", ""), p2.get("d", ""), p2.get("a", ""), p2.get("s", "")))
    return sentence(out) or tr("st.nostats")


def world(p, tr):
    out = []
    t = p.get("time")
    if present(t) and isinstance(t, dict):
        text = "%s %s" % (clean(t.get("h")), clean(t.get("tod")))
        if t.get("l"):
            text += ", " + clean(t.get("l"))
        out.append(text)
    d = p.get("date")
    if present(d) and isinstance(d, dict):
        text = "%s %s" % (clean(d.get("d")), clean(d.get("m")))
        if d.get("s"):
            text += ", " + clean(d.get("s"))
        out.append(text)
    w = p.get("w")
    if present(w) and isinstance(w, dict) and w.get("m"):
        out.append(clean(w.get("m")))
    return sentence(out) or tr("st.noworld")


def location(p, tr):
    out = []
    if present(p.get("room")):
        out.append(clean(p.get("room")))
    if present(p.get("zone")):
        out.append(clean(p.get("zone")))
    ex = p.get("exits")
    if present(ex) and isinstance(ex, dict):
        visible = str(ex.get("e") or "").lower()
        hidden = str(ex.get("h") or "").lower()
        words = [tr("dir." + name) for letter, name in EXIT_LETTERS if letter in visible]
        secret = [tr("dir." + name) for letter, name in EXIT_LETTERS if letter in hidden and letter not in visible]
        text = tr("st.exits", ", ".join(words)) if words else tr("st.noexits")
        if secret:
            text += " " + tr("st.hidden", ", ".join(secret))
        out.append(text)
    return sentence(out) or tr("st.noplace")


def who(p, tr):
    w = p.get("who")
    if not present(w) or not isinstance(w, dict):
        return tr("st.nowho")
    names = [clean(x.get("n")) for x in w.get("p") or [] if isinstance(x, dict) and x.get("n")]
    head = tr("st.who", w.get("v", len(names)), w.get("t", len(names)))
    return head + " " + ", ".join(names) if names else head


def fight_commands(p):
    cmds = p.get("fcmd")
    return [str(c) for c in cmds] if isinstance(cmds, list) else []


PANELS = (("affects", affects), ("quests", quests), ("group", group), ("stats", stats),
          ("world", world), ("location", location), ("who", who))


def everything(p, tr):
    return "\n\n".join("%s\n%s" % (tr("st.title." + key), fn(p, tr)) for key, fn in PANELS)
