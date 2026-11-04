"""Lists built from the server's "list" frame.

The server sends {"command": "list", "args": [LIST]} next to the text of a list
command (format: dreamland_code docs/web-list-frame.md). Rows carry English
commands and verbs, so the list works the same in every game language. The rows
returned here have the shape ItemsDialog and MainFrame.item_action already use.
"""

# verb: (label key, Alt letter or None, effect). "refresh" re-reads the list after
# the command, "close" closes it, "open" opens the reply as a list of the same kind,
# "target" and "input" put the command into the command field for the player to
# finish, with a name or with a message.
VERBS = {
    "practice": ("tl.practice", "P", "refresh"),
    "help": ("tl.help", "H", None),
    "read": ("tl.read", "R", None),
    "open": ("tl.openlist", None, "open"),
    "do": ("tl.dosocial", "B", None),
    "social_at": ("tl.socialat", None, "target"),
    "get": ("tl.get", "G", "refresh"),
    "filter": ("tl.filter", "F", "open"),
    "look": ("tl.look", "L", None),
    "whois": ("tl.whois", "W", None),
    "tell": ("tl.tell", "T", "input"),
    "path": ("tl.path", "A", None),
    "request": ("tl.request", "B", "close"),
    "buy": ("tl.buy", "B", "refresh"),
}


def row_label(row, tr, kind):
    label = str(row.get("label") or row.get("id") or "")
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    if kind == "skills":
        if data.get("level"):
            label += ", " + tr("tl.level", data["level"])
        if data.get("mana"):
            label += ", " + tr("tl.cost", data["mana"])
        elif data.get("moves"):
            label += ", " + tr("tl.cost", tr("tl.moves", data["moves"]))
    elif row.get("section"):
        label += ", " + str(row["section"])
    return label


def rows_from_frame(lst, tr, kind):
    """Turn a LIST into dialog rows; kind is the client list kind it answers."""
    rows = []
    for row in lst.get("rows") or []:
        if not isinstance(row, dict):
            continue
        out = {"label": row_label(row, tr, lst.get("kind")), "kind": "custom", "menu": [], "keys": {},
               "refresh": set()}
        used = set()
        for action in row.get("actions") or []:
            if not isinstance(action, dict) or not action.get("cmd"):
                continue
            verb, cmd = str(action.get("verb") or ""), str(action["cmd"])
            key, letter, effect = VERBS.get(verb, (None, None, None))
            label = tr(key) if key else cmd
            if effect in ("target", "input"):
                cmd = "__%s__ %s" % (effect, cmd)
            out["menu"].append((label, cmd))
            if letter and letter not in used:
                used.add(letter)
                out["keys"][(ord(letter), True)] = [cmd]
            if effect == "refresh":
                out["refresh"].add(cmd)
            elif effect == "close":
                out["close"] = True
            elif effect == "open" and "open" not in out:
                out["open"] = (kind, cmd)
        rows.append(out)
    return rows
