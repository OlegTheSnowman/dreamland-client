import re

SHOP_ROW = re.compile(r"^\s*(\d+)\.\s+(\S.*)$")
SERVICE_ROW = re.compile(r"^\s*(service\s+\S+)\s{2,}(\S.*)$", re.I)
TRAIN_ROW = re.compile(r"^\s*(?:(train\s+(\w+))|(\w+))\s*:\s*(\S.*)$", re.I)
LEARNED = re.compile(r"(\d+)\s*\(\s*(\d+)\s*\)")


def quoted(name):
    return "'%s'" % name if " " in name else name


def shop(lines, tr):
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


def services(lines, tr):
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


def training(lines, tr):
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


def skills(lines, tr):
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
            if not name or not m:
                continue
            label = tr("tl.skill", name, m.group(1))
            if m.group(2) != m.group(1):
                label += " " + tr("tl.bonus", m.group(2))
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


def quest_shop(lines, tr):
    rows, section = [], ""
    for line in lines:
        text = line.text.strip()
        m = QSHOP_ROW.match(text)
        if m:
            n, name, cost = m.group(1), m.group(2), m.group(4)
            label = "%s. %s, %s" % (n, name, cost) + (" (%s)" % section if section else "")
            rows.append({"label": label, "kind": "custom", "menu": [(tr("tl.buy"), "quest buy " + n)],
                         "keys": {(ord("B"), True): ["quest buy " + n]}, "refresh": {"quest buy " + n}})
        elif text and not re.match(r"^(You |To buy|List of|.*asks? .* show)", text) and ":" not in text:
            section = text
    return rows


def quest_request(lines, tr):
    rows = []
    for line in lines:
        m = QREQ_ROW.match(line.text)
        if m:
            cmd = "quest request " + m.group(1)
            rows.append({"label": "%s, %s" % (m.group(2).strip(), m.group(3).strip()), "kind": "custom",
                         "menu": [(tr("tl.request"), cmd)], "keys": {(ord("B"), True): [cmd]}, "refresh": set()})
    return rows


def zone_quests(lines, tr):
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


def areas(lines, tr):
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
