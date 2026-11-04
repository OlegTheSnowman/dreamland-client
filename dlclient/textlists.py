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


PARSERS = {"shop": ("list", shop, "tl.shop", "tl.shopkeys"),
           "services": ("service", services, "tl.services", "tl.servicekeys"),
           "training": ("train", training, "tl.training", "tl.trainkeys"),
           "skills": ("practice", skills, "tl.skills", "tl.skillkeys")}
