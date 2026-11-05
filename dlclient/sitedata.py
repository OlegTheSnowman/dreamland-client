"""Game knowledge from the public website: zone quests, class skill trees,
religions, races and the item database.

Items come from the site's JSON item database. Quests, skills, religions and
races exist only as help article text, so they are read from the help bodies
(the same files help search uses). Every article of one kind is written the
same way, "* Label: value" lines in all three languages, so the labels below are
all the parsing needs. Files are cached under the client's folder and refreshed
at most once a day, in the background.
"""
import html
import json
import os
import re
import threading
import time
import urllib.request

BASE = "https://dreamland.rocks/data/"
MAX_AGE = 24 * 3600
LANGS = ("en", "ua", "ru")

# Per language: the words the help uses for each field.
LABELS = {
    "en": {"levels": "Levels", "danger": "Danger", "route": "How to get there", "quests": "Quests",
           "qlevels": "Levels", "from": "from", "to": "to", "align": "Alignment", "often": "How often",
           "requires": "First complete the quest", "stats": "Stats", "classes": "Classes",
           "resist": "Resistant", "vuln": "Vulnerable", "size": "Size", "paths": "Paths",
           "patron": "Patron of", "gifts": "Gifts", "restrict": "Restrictions", "level": "Level"},
    "ua": {"levels": "Рівні", "danger": "Небезпека", "route": "Як дістатися", "quests": "Завдання",
           "qlevels": "Рівні", "from": "з", "to": "по", "align": "Натура", "often": "Як часто",
           "requires": "Спершу виконай завдання", "stats": "Параметри", "classes": "Класи",
           "resist": "Стійкий", "vuln": "Вразливий", "size": "Розмір", "paths": "Шляхи",
           "patron": "Підопічні", "gifts": "Дари", "restrict": "Обмеження", "level": "Рівень"},
    "ru": {"levels": "Уровни", "danger": "Опасность", "route": "Как добраться", "quests": "Задания",
           "qlevels": "Уровни", "from": "с", "to": "по", "align": "Натура", "often": "Как часто",
           "requires": "Сначала выполни задание", "stats": "Параметры", "classes": "Классы",
           "resist": "Устойчивы", "vuln": "Уязвимы", "size": "Размер", "paths": "Пути",
           "patron": "Подопечные", "gifts": "Дары", "restrict": "Ограничения", "level": "Уровень"},
}


def folder():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "DreamLandClient", "sitedata")
    os.makedirs(path, exist_ok=True)
    return path


def files_for(lang):
    return ["help-index.json", "help-body-%s.json" % lang, "db_weapon.json", "db_armor.json"]


_lock = threading.Lock()


def _readable(path):
    try:
        with open(path, encoding="utf-8") as f:
            json.load(f)
        return True
    except (OSError, ValueError):
        return False


def refresh(lang, force=False, timeout=30):
    """Download whatever is missing, broken or older than a day. Returns True if all are there."""
    if os.environ.get("DLCLIENT_QUIET"):
        return all(os.path.exists(os.path.join(folder(), f)) for f in files_for(lang))
    with _lock:
        return _refresh(lang, force, timeout)


def _refresh(lang, force, timeout):
    ok = True
    for name in files_for(lang):
        path = os.path.join(folder(), name)
        fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < MAX_AGE
        if fresh and not force and _readable(path):
            continue
        try:
            req = urllib.request.Request(BASE + name, headers={"User-Agent": "DreamLand desktop client"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(40_000_000)
            json.loads(body.decode("utf-8"))
            with open(path + ".tmp", "wb") as f:
                f.write(body)
            os.replace(path + ".tmp", path)
        except Exception:
            ok = ok and _readable(path)
    return ok


def strip(text):
    """Game markup to plain text."""
    return html.unescape(re.sub(r"<[^>]+>", "", text or ""))


def header(text, lang=None):
    """The '* Label: value' lines of an article, by label."""
    out = {}
    for line in strip(text).splitlines():
        m = re.match(r"^\s*\*\s*([^:]{2,40}):\s*(.+?)\s*$", line)
        if m:
            out.setdefault(m.group(1).strip(), m.group(2).strip())
    return out


class Site:
    def __init__(self, lang, index, body, weapons, armor):
        self.lang = lang if lang in LABELS else "en"
        self.L = LABELS[self.lang]
        self.index = index
        self.body = body
        self.weapons = weapons
        self.armor = armor

    @classmethod
    def load(cls, lang):
        lang = lang if lang in LANGS else "en"
        d = folder()

        def read(name, default):
            try:
                with open(os.path.join(d, name), encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return default
        return cls(lang, read("help-index.json", []), read("help-body-%s.json" % lang, {}),
                   read("db_weapon.json", []), read("db_armor.json", []))

    def ready(self):
        return bool(self.index and self.body)

    def title(self, entry):
        return (entry.get("toc") or {}).get(self.lang) or (entry.get("toc") or {}).get("en") or str(entry["id"])

    def articles(self, label):
        return [e for e in self.index if label in (e.get("labels") or []) and str(e["id"]) in self.body]

    # Zone quests ---------------------------------------------------------
    def zone_quests(self):
        L = self.L
        out = []
        for e in self.articles("area"):
            text = strip(self.body[str(e["id"])])
            head = header(self.body[str(e["id"])], self.lang)
            zone = {"zone": self.title(e), "zone_id": e["id"], "levels": head.get(L["levels"], ""),
                    "danger": head.get(L["danger"], ""),
                    "route": re.sub(r"\s*\(.*\)\s*$", "", head.get(L["route"], ""))}
            m = re.search(r"^%s:\s*$" % re.escape(L["quests"]), text, re.M)
            if not m:
                continue
            items, cur = [], None
            for line in text[m.end():].splitlines():
                s = line.strip()
                if not s:
                    if cur is not None:
                        items.append(cur)
                        cur = None
                    continue
                if s.startswith("* "):
                    if cur is not None:
                        items.append(cur)
                    cur = s[2:]
                elif cur is not None:
                    cur += " " + s
            if cur is not None:
                items.append(cur)
            for raw in items:
                out.append(dict(zone, **self.parse_quest(raw)))
        return out

    def parse_quest(self, raw):
        L = self.L
        q = {"text": raw, "low": 0, "high": 0, "align": "", "often": "", "requires": ""}
        m = re.search(r"\s%s:\s*%s\s*(\d+)(?:\s*%s\s*(\d+))?\.?" % (
            re.escape(L["qlevels"]), re.escape(L["from"]), re.escape(L["to"])), raw)
        if m:
            q["text"] = raw[:m.start()].strip()
            q["low"] = int(m.group(1))
            q["high"] = int(m.group(2)) if m.group(2) else 0
        for key, label in (("align", L["align"]), ("often", L["often"]), ("requires", L["requires"])):
            m2 = re.search(r"%s:\s*(.+?)(?=\.\s+[A-ZА-ЯІЇЄҐ][^.]{1,40}:|$)" % re.escape(label), raw)
            if m2:
                q[key] = m2.group(1).strip().rstrip(".")
        return q

    # Class skill trees ---------------------------------------------------
    def class_names(self):
        names = []
        for e in self.index:
            en = (e.get("toc") or {}).get("en", "")
            if en.endswith(" skills") and e.get("cat") == "classes":
                names.append(en[:-len(" skills")])
        return sorted(set(names))

    def class_skills(self, cls_en):
        """[(level, [skill names])] for the class's 'skills' article."""
        e = next((x for x in self.index if (x.get("toc") or {}).get("en", "").lower() == cls_en.lower() + " skills"), None)
        if not e or str(e["id"]) not in self.body:
            return []
        out = []
        for line in strip(self.body[str(e["id"])]).splitlines():
            m = re.match(r"^\s*%s\s+(\d+):\s*(.+)$" % re.escape(self.L["level"]), line)
            if m:
                out.append((int(m.group(1)), [s.strip() for s in m.group(2).split(",") if s.strip()]))
        return out

    def class_skill_list(self, cls_en):
        """[{level, name, id}] for every skill of the class, with its help article id."""
        e = next((x for x in self.index if (x.get("toc") or {}).get("en", "").lower() == cls_en.lower() + " skills"), None)
        if not e or str(e["id"]) not in self.body:
            return []
        out = []
        for raw in self.body[str(e["id"])].split("\n"):
            m = re.match(r"^\s*%s\s+(\d+):\s*(.+)$" % re.escape(self.L["level"]), strip(raw))
            if not m:
                continue
            names = [x.strip() for x in m.group(2).split(",") if x.strip()]
            ids = [int(i) for i in re.findall(r"<hh id='(\d+)'>", raw)]
            for i, name in enumerate(names):
                out.append({"level": int(m.group(1)), "name": name, "id": ids[i] if len(ids) == len(names) else None})
        return out

    def skill_teachers(self):
        """Skill help id -> {group, teacher, zone_id}, from the skill group articles.

        Each group article has one line naming its teacher (or the guild) in the
        teacher colour, with a link to the teacher's zone when there is one."""
        if getattr(self, "_teachers", None) is not None:
            return self._teachers
        areas = {e["id"] for e in self.index if "area" in (e.get("labels") or [])}
        out = {}
        for e in self.articles("skillgroup"):
            raw = self.body[str(e["id"])]
            line = next((x for x in raw.split("\n") if re.search(r"<c c='fgdg'>[^<\s]", x)), "")
            zone = next((int(i) for i in re.findall(r"<hh id='(\d+)'>", line) if int(i) in areas), None)
            info = {"group": self.title(e), "group_id": e["id"],
                    "teacher": re.sub(r"\s+", " ", strip(line)).strip(" -"), "zone_id": zone}
            for i in re.findall(r"<hh id='(\d+)'>", raw):
                out.setdefault(int(i), info)
        self._teachers = out
        return out

    def zone_names(self, ident):
        """A zone's names in every language, for finding it in the area list."""
        e = next((x for x in self.index if x.get("id") == ident), None)
        if not e:
            return []
        toc = e.get("toc") or {}
        return [n for n in (self.title(e), toc.get("en"), toc.get("ru"), toc.get("ua")) if n]

    # Religions and races -------------------------------------------------
    def religions(self):
        L = self.L
        out = []
        for e in self.articles("religion"):
            head = header(self.body[str(e["id"])], self.lang)
            if L["paths"] not in head and L["gifts"] not in head:
                continue
            out.append({"name": self.title(e), "id": e["id"], "paths": head.get(L["paths"], ""),
                        "patron": head.get(L["patron"], ""), "gifts": head.get(L["gifts"], ""),
                        "restrict": head.get(L["restrict"], "")})
        return sorted(out, key=lambda r: r["name"].lower())

    def races(self):
        L = self.L
        out = []
        for e in self.articles("race"):
            head = header(self.body[str(e["id"])], self.lang)
            if L["stats"] not in head:
                continue
            out.append({"name": self.title(e), "id": e["id"], "align": head.get(L["align"], ""),
                        "stats": head.get(L["stats"], ""), "classes": head.get(L["classes"], ""),
                        "resist": head.get(L["resist"], ""), "vuln": head.get(L["vuln"], ""),
                        "size": head.get(L["size"], "")})
        return sorted(out, key=lambda r: r["name"].lower())

    # Items ---------------------------------------------------------------
    def item_name(self, it):
        return it.get({"en": "nameEn", "ua": "nameUa"}.get(self.lang, "name")) or it.get("name", "")

    def item_place(self, it):
        area = it.get({"en": "areaEn", "ua": "areaUa"}.get(self.lang, "area")) or it.get("area", "")
        where = it.get({"en": "whereEn", "ua": "whereUa"}.get(self.lang, "where")) or it.get("where", "")
        return area, where

    def items(self, kind, low, high, align=None, slot=None, wclass=None):
        """Weapons or armor between low and high level, usable by align ('good', 'neutral', 'evil')."""
        src = self.weapons if kind == "weapon" else self.armor
        out = []
        for it in src:
            lvl = num(it.get("level"))
            if lvl is None or not low <= lvl <= high:
                continue
            if slot and it.get("wearloc") != slot:
                continue
            if wclass and it.get("wclass") != wclass:
                continue
            if align and not usable_by(it.get("align"), align):
                continue
            out.append(it)
        return sorted(out, key=lambda it: (-num(it["level"]), self.item_name(it).lower()))

    def slots(self, kind):
        src = self.weapons if kind == "weapon" else self.armor
        key = "wclass" if kind == "weapon" else "wearloc"
        return sorted({it[key] for it in src if isinstance(it.get(key), str) and it[key]})

    def article_text(self, ident):
        return strip(self.body.get(str(ident), "")).strip()


ALIGN_CODES = {"good": ("g", "good", "добр"), "neutral": ("n", "neutral", "нейтр"), "evil": ("e", "evil", "зл")}


def usable_by(field, align):
    """The item database lists who may use an item; empty or '-' means anyone."""
    f = (field or "").strip().lower()
    if f in ("", "-"):
        return True
    return any(code in f for code in ALIGN_CODES.get(align, ()))


def num(v):
    """Numbers in the item database are ints or strings; '-' means none."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def align_ok(text, align):
    """Whether a quest's free-text alignment (any language) allows align."""
    t = (text or "").lower()
    if not t or not align:
        return True
    if not any(w in t for codes in ALIGN_CODES.values() for w in codes[1:]):
        return True
    return any(w in t for w in ALIGN_CODES.get(align, ())[1:])


def word(tr, prefix, value):
    """A database word (sword, torso, hit) in the user's language, or as is."""
    if not tr or not value:
        return value
    key = prefix + value.replace(" ", "_")
    text = tr(key)
    return value if text == key else text


def stat_text(it, tr=None):
    """'hit +1, dam +2, str +1' from an item record."""
    parts = []
    for key, label in (("hr", "hit"), ("dr", "dam"), ("hp", "hp"), ("mana", "mana"), ("move", "mv"),
                       ("saves", "saves"), ("stat_str", "str"), ("stat_int", "int"), ("stat_wis", "wis"),
                       ("stat_dex", "dex"), ("stat_con", "con"), ("stat_cha", "cha")):
        v = num(it.get(key))
        if v:
            parts.append("%s %+d" % (word(tr, "guide.stat.", label), v))
    return ", ".join(parts)
