import json
import re
import urllib.error
import urllib.request

GRAPH_BASE = "https://dreamland.rocks/maps/graph/"
COLOUR = re.compile(r"\{.")


class NoMap(Exception):
    pass


def area_key(area_file):
    return re.sub(r"\.are$", "", area_file or "")


def fetch_rooms(area_file, lang, timeout=15):
    key = area_key(area_file)
    if not key or not re.fullmatch(r"[a-z0-9_-]+", key):
        raise NoMap(key)
    req = urllib.request.Request(GRAPH_BASE + "area-%s.json" % key,
                                 headers={"User-Agent": "DreamLand desktop client"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read(10_000_000).decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise NoMap(key) from e
    except ValueError as e:
        raise NoMap(key) from e
    rooms = data.get("rooms") or {}
    items = rooms.values() if isinstance(rooms, dict) else rooms
    out = []
    for room in items:
        if not isinstance(room, dict) or "vnum" not in room:
            continue
        name = room.get("name") or ""
        if lang != "ru":
            name = ((room.get("i18n") or {}).get(lang) or {}).get("name") or name
        name = COLOUR.sub("", name).strip()
        if name:
            out.append((int(room["vnum"]), name))
    out.sort(key=lambda r: (r[1].lower(), r[0]))
    return out


INDEX_URL = "https://dreamland.rocks/maps/index.json"
ROUTE = re.compile(r"[0-9neswudNESWUD]+")
MARKET_SQUARE = 3014
MIDGAARD = "midgaard"


def fetch_areas(lang, timeout=15):
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": "DreamLand desktop client"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read(5_000_000).decode("utf-8"))
    out = []
    for e in data if isinstance(data, list) else []:
        if not isinstance(e, dict) or not e.get("file"):
            continue
        en = COLOUR.sub("", str(e.get("credits") or "")).strip()
        ru = COLOUR.sub("", str(e.get("name") or "")).strip()
        sw = str(e.get("sw") or "").strip()
        out.append({
            "file": area_key(e["file"]),
            "name": (en if lang == "en" else ru) or en or ru,
            "en": en,
            "ru": ru,
            "min": int(e.get("levMin") or 0),
            "max": int(e.get("levMax") or 0),
            "levels": bool(e.get("showLevels", True)),
            "route": sw if ROUTE.fullmatch(sw) else None,
        })
    out.sort(key=lambda a: a["name"].lower())
    return out
