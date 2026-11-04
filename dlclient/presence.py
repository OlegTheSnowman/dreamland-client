CREATURE_WORDS = {"consider", "follow", "шансы", "следовать", "шанси", "слідувати", "оценить", "оцінити"}
TARGET_MARKS = ("[TARGET]", "[ЦЕЛЬ]", "[ЦІЛЬ]")


def classify(lines):
    found = set()
    for line in lines:
        text = line.text
        if any(mark in text for mark in TARGET_MARKS):
            found.add("target")
        for link in line.links:
            if not link.menu:
                continue
            ident = getattr(link, "ident", "") or ""
            if ident and not ident.isdigit():
                found.add("player")
                continue
            words = {entry[1].split()[0].lower() for entry in link.menu if entry and entry[1].split()}
            found.add("mob" if words & CREATURE_WORDS else "item")
    return found
