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
QREQ_ROW = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*\(([^)]*)\)\s*$")
ZQUEST_HEAD = re.compile(r"^\[\s*(\d+)\]\s+(.+)$")
AREA_CELL = re.compile(r"(\S(?:.*?\S)?)\s{2,}(\d+-\d+)?\s*(safe|easy|hard|deadly)\b")


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


def quest_request(lines, tr, command=""):
    rows = []
    for line in lines:
        m = QREQ_ROW.match(line.text)
        if m:
            cmd = "quest request " + m.group(1)
            rows.append({"label": "%s, %s" % (m.group(2).strip(), m.group(3).strip()), "kind": "custom",
                         "menu": [(tr("tl.request"), cmd)], "keys": {(ord("B"), True): [cmd]}, "refresh": set(),
                         "close": True})
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


def areas(lines, tr, command=""):
    rows = []
    for line in lines:
        for m in AREA_CELL.finditer(line.text):
            name = m.group(1).strip()
            label = name + (", levels %s" % m.group(2) if m.group(2) else "") + ", " + m.group(3)
            rows.append({"label": label, "kind": "custom", "menu": [(tr("tl.help"), "help " + name)],
                         "keys": {(ord("H"), True): ["help " + name]}, "refresh": set()})
    return rows


PARSERS = {"shop": ("list", shop, "tl.shop", "tl.shopkeys"),
           "services": ("service", services, "tl.services", "tl.servicekeys"),
           "training": ("train", training, "tl.training", "tl.trainkeys"),
           "skills": ("practice", skills, "tl.skills", "tl.skillkeys"),
           "skilltable": ("skills", skills, "tl.skills", "tl.skillkeys"),
           "questshop": ("quest list", quest_shop, "tl.questshop", "tl.questshopkeys"),
           "questrequest": ("quest request", quest_request, "tl.questrequest", "tl.questrequestkeys"),
           "zonequests": ("quest", zone_quests, "tl.zonequests", "tl.zonequestkeys"),
           "areas": ("areas", areas, "tl.areas", "tl.areakeys")}


NOTE_ROW = re.compile(r"^\[(\d+)\s*\]\s*(.*)$")
HELP_ROW = re.compile(r"^\[\s*(\d+)\]\s+(\S.*)$")
SOCIAL_ROW = re.compile(r"^(\S+) -- (\S.*)$")
SECTION_ROW = re.compile(r"^([^:]{2,40}):\s+(\S.*)$")
PAGER = ("Press Enter to continue", "Нажмите клавишу Enter для продолжения", "Натисни Enter, щоб продовжити")


def is_pager(text):
    return any(p in text for p in PAGER)


def notes(lines, tr, command=""):
    board = (command.split() or ["note"])[0]
    rows = []
    for line in lines:
        m = NOTE_ROW.match(line.text.strip())
        if m:
            cmd = "%s read %s" % (board, m.group(1))
            rows.append({"label": "%s. %s" % (m.group(1), m.group(2).strip() or "-"), "kind": "custom",
                         "menu": [(tr("tl.read"), cmd)], "keys": {(ord("R"), True): [cmd]}, "refresh": set()})
    return rows


def help_matches(lines, tr, command=""):
    rows = []
    for line in lines:
        m = HELP_ROW.match(line.text.strip())
        if m:
            cmd = "help " + m.group(1)
            rows.append({"label": m.group(2), "kind": "custom", "menu": [(tr("tl.read"), cmd)],
                         "keys": {(ord("R"), True): [cmd]}, "refresh": set(), "close": True})
    return rows


def skill_groups(lines, tr, command=""):
    rows = []
    if len(command.split()) > 1:
        started = False
        for line in lines:
            text = line.text.strip()
            if text.endswith(":") and not started:
                started = True
                continue
            if not started or not text:
                continue
            for name in re.split(r"\s{2,}", text):
                name = name.strip()
                if name:
                    q = quoted(name)
                    rows.append({"label": name, "kind": "custom",
                                 "menu": [(tr("tl.help"), "help " + name), (tr("tl.practice"), "practice " + q)],
                                 "keys": {(ord("H"), True): ["help " + name], (ord("P"), True): ["practice " + q]},
                                 "refresh": set()})
        return rows
    for line in lines:
        if line.text.startswith("    ") and line.text.strip():
            name = line.text.strip()
            rows.append({"label": name, "kind": "custom", "menu": [(tr("tl.openlist"), "glist " + name)],
                         "keys": {}, "refresh": set(), "open": ("glist", "glist " + name)})
    return rows


def socials(lines, tr, command=""):
    rows = []
    for line in lines:
        m = SOCIAL_ROW.match(line.text.strip())
        if m:
            name = m.group(1)
            rows.append({"label": "%s, %s" % (name, m.group(2)), "kind": "custom",
                         "menu": [(tr("tl.dosocial"), name), (tr("tl.socialat"), "__target__ " + name),
                                  (tr("tl.helpsocial"), "help " + name)],
                         "keys": {(ord("B"), True): [name], (ord("H"), True): ["help " + name]},
                         "target": name, "refresh": set()})
    return rows


def command_summary(lines, tr, command=""):
    rows = []
    for line in lines:
        m = SECTION_ROW.match(line.text.strip())
        if not m or m.group(1).startswith(("Full list", "All help")):
            continue
        for name in m.group(2).split():
            if len(name) > 1:
                rows.append({"label": "%s, %s" % (name, m.group(1)), "kind": "custom",
                             "menu": [(tr("tl.help"), "help " + name)], "keys": {(ord("H"), True): ["help " + name]},
                             "refresh": set()})
    return rows


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
    "notes": ("note list", notes, "tl.notes", "tl.notekeys"),
    "helpmatches": ("help", help_matches, "tl.helpmatches", "tl.helpkeys"),
    "glist": ("glist", skill_groups, "tl.glist", "tl.glistkeys"),
    "socials": ("socials", socials, "tl.socials", "tl.socialkeys"),
    "commands": ("commands", command_summary, "tl.commands", "tl.commandkeys"),
    "linked": ("vault", linked, "tl.linked", "tl.linkedkeys"),
})
