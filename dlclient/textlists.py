import re

SHOP_ROW = re.compile(r"^\s*(\d+)\.\s+(\S.*)$")
SERVICE_ROW = re.compile(r"^\s*(service\s+\S+)\s{2,}(\S.*)$", re.I)
TRAIN_ROW = re.compile(r"^\s*(?:(train\s+(\w+))|(\w+))\s*:\s*(\S.*)$", re.I)
LEARNED = re.compile(r"(\d+)\s*\(\s*(\d+)\s*\)")


def quoted(name):
    return "'%s'" % name if " " in name else name


def shop(lines, tr, command=""):
    rows = []
    for line in lines:
        m = SHOP_ROW.match(line.text)
        if not m:
            continue
        n, desc = m.group(1), m.group(2).strip()
        rows.append({"label": "%s. %s" % (n, desc), "kind": "custom",
                     "menu": [(tr("tl.buy"), "buy " + n), (tr("tl.properties"), "properties " + n)],
                     "keys": {(ord("B"), True): ["buy " + n], (ord("P"), True): ["properties " + n]},
                     "refresh": {"buy " + n}})
    return rows


def services(lines, tr, command=""):
    rows = []
    for line in lines:
        m = SERVICE_ROW.match(line.text)
        if not m:
            continue
        cmd, price = " ".join(m.group(1).split()), m.group(2).strip()
        name = cmd.split(" ", 1)[1]
        rows.append({"label": "%s, %s" % (name, price), "kind": "custom",
                     "menu": [(tr("tl.order"), cmd)], "keys": {(ord("B"), True): [cmd]}, "refresh": set()})
    return rows


def training(lines, tr, command=""):
    rows = []
    for line in lines:
        m = TRAIN_ROW.match(line.text)
        if not m or not ("/" in m.group(4)):
            continue
        cmd = " ".join(m.group(1).split()) if m.group(1) else ""
        stat = m.group(2) or m.group(3)
        state = " ".join(m.group(4).split())
        row = {"label": "%s %s" % (stat, state), "kind": "custom", "menu": [], "keys": {}, "refresh": set()}
        if cmd:
            row["menu"] = [(tr("tl.train"), cmd)]
            row["keys"] = {(ord("B"), True): [cmd]}
            row["refresh"] = {cmd}
        rows.append(row)
    return rows


def skills(lines, tr, command=""):
    rows = []
    level = ""
    for line in lines:
        if "|" not in line.text:
            continue
        cells = [c.strip() for c in line.text.split("|")]
        if len(cells) < 4:
            continue
        if cells[0].isdigit():
            level = cells[0]
        for i in range(1, len(cells) - 2, 3):
            name, learned, cost = cells[i], cells[i + 1], cells[i + 2]
            m = LEARNED.search(learned)
            if not name or not (m or learned.lower() == "n/a"):
                continue
            if m:
                label = tr("tl.skill", name, m.group(1))
                if m.group(2) != m.group(1):
                    label += " " + tr("tl.bonus", m.group(2))
            else:
                label = tr("tl.notyet", name)
            if level:
                label += ", " + tr("tl.level", level)
            if cost:
                label += ", " + tr("tl.cost", cost)
            q = quoted(name)
            rows.append({"label": label, "kind": "custom",
                         "menu": [(tr("tl.practice"), "practice " + q), (tr("tl.help"), "help " + name)],
                         "keys": {(ord("P"), True): ["practice " + q], (ord("H"), True): ["help " + name]},
                         "refresh": {"practice " + q}})
    return rows


QSHOP_ROW = re.compile(r"^\s*(\d+)\.\s+(.+?), word (\S+):\s*(.+?)\.?$")
ZQUEST_HEAD = re.compile(r"^\[\s*(\d+)\]\s+(.+)$")


def quest_shop(lines, tr, command=""):
    rows, section = [], ""
    for line in lines:
        text = line.text.strip()
        m = QSHOP_ROW.match(text)
        if m:
            n, name, word, cost = m.group(1), m.group(2), m.group(3), m.group(4)
            label = "%s. %s, %s, %s" % (n, name, tr("tl.word", word), cost) + (" (%s)" % section if section else "")
            rows.append({"label": label, "kind": "custom", "menu": [(tr("tl.buy"), "quest buy " + n)],
                         "keys": {(ord("B"), True): ["quest buy " + n]}, "refresh": {"quest buy " + n}})
        elif text and not re.match(r"^(You |To buy|List of|.*asks? .* show)", text) and ":" not in text:
            section = text
    return rows


def zone_quests(lines, tr, command=""):
    rows, cur = [], None
    for line in lines:
        text = line.text.strip()
        m = ZQUEST_HEAD.match(text)
        if m:
            n = m.group(1)
            cur = {"label": m.group(2), "kind": "custom",
                   "menu": [(tr("tl.details"), "quest " + n), None, (tr("tl.cancelquest"), "quest cancel " + n)],
                   "keys": {(ord("L"), True): ["quest " + n]}, "refresh": {"quest cancel " + n}}
            rows.append(cur)
        elif cur is not None and text and not text.startswith("Commands:"):
            cur["label"] += (". " if cur.get("first", True) else " ") + text
            cur["first"] = False
        elif text.startswith("Commands:"):
            cur = None
    return rows


# A parser of None means the server sends the list as a "list" frame
# (framelists.py); without a frame the game's own text is shown.
PARSERS = {"shop": ("list", shop, "tl.shop", "tl.shopkeys"),
           "services": ("service", services, "tl.services", "tl.servicekeys"),
           "training": ("train", training, "tl.training", "tl.trainkeys"),
           "skills": ("practice", skills, "tl.skills", "tl.skillkeys"),
           "skilltable": ("skills", None, "tl.skills", "tl.skillkeys"),
           "questshop": ("quest list", quest_shop, "tl.questshop", "tl.questshopkeys"),
           "questrequest": ("quest request", None, "tl.questrequest", "tl.questrequestkeys"),
           "zonequests": ("quest", zone_quests, "tl.zonequests", "tl.zonequestkeys"),
           "areas": ("areas", None, "tl.areas", "tl.areakeys")}


PAGER = ("Press Enter to continue", "Нажмите клавишу Enter для продолжения", "Натисни Enter, щоб продовжити")


def is_pager(text):
    return any(p in text for p in PAGER)


def linked(lines, tr, command=""):
    rows = []
    for line in lines:
        cmds = [(l.label, l.command) for l in line.links if l.command and not l.menu and not l.url]
        if not cmds:
            continue
        rows.append({"label": " ".join(line.text.split()), "kind": "custom",
                     "menu": [("%s: %s" % (label, cmd) if label != cmd else cmd, cmd) for label, cmd in cmds],
                     "keys": {}, "refresh": {cmd for _, cmd in cmds if cmd.split()[:2] in (["vault", "get"],)}})
    return rows


PARSERS.update({
    "notes": ("note list", None, "tl.notes", "tl.notekeys"),
    "helpmatches": ("help", None, "tl.helpmatches", "tl.helpkeys"),
    "glist": ("glist", None, "tl.glist", "tl.glistkeys"),
    "socials": ("socials", None, "tl.socials", "tl.socialkeys"),
    "commands": ("commands", None, "tl.commands", "tl.commandkeys"),
    "linked": ("vault", linked, "tl.linked", "tl.linkedkeys"),
})
