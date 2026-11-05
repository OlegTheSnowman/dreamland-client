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
    data = fetch_graph(area_file, timeout)
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



INDEX_URL = "https://dreamland.rocks/data/maps-index.json"
ROUTE = re.compile(r"[0-9neswudNESWUD]+")
MARKET_SQUARE = 3014
MIDGAARD = "midgaard"
DANGER = ("safe", "easy", "hard", "deadly")


ROUTE_HEAD = re.compile(r"^([0-9neswudNESWUD]+)(?:$|\s*[,;]|\s+(?:or|and|или|або|и|і|та|й)\b)", re.I)


PARTS = re.compile(r"(?:^|,\s*)([^,:]{1,30}?):\s*([0-9neswudNESWUD]+)(?=\s*(?:,|$))")


def split_parts(text):
    text = text or ""
    found = list(PARTS.finditer(text))
    if len(found) < 2:
        return []
    tail = text[found[-1].end():].strip(" ,;")
    return [(m.group(1).strip(), m.group(2), tail if m is found[-1] else "") for m in found]


def split_route(text):
    text = (text or "").strip()
    if ROUTE.fullmatch(text):
        return text, ""
    m = ROUTE_HEAD.match(text)
    if m:
        return m.group(1), text[m.end(1):].strip(" ,;")
    return None, text


def route_steps(route):
    total = 0
    for count, letter in re.findall(r"(\d*)([neswudNESWUD])", route or ""):
        total += int(count) if count else 1
    return total


def _get_json(url, limit, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "DreamLand desktop client"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(limit).decode("utf-8"))


def fetch_graph(area_file, timeout=15):
    key = area_key(area_file)
    if not key or not re.fullmatch(r"[a-z0-9_-]+", key):
        raise NoMap(key)
    try:
        return _get_json(GRAPH_BASE + "area-%s.json" % key, 20_000_000, timeout)
    except (urllib.error.HTTPError, ValueError) as e:
        raise NoMap(key) from e


def fetch_areas(lang, timeout=15):
    data = _get_json(INDEX_URL, 5_000_000, timeout)
    suffix = {"en": "En", "ua": "Ua"}.get(lang, "")
    out = []
    for e in data if isinstance(data, list) else []:
        if not isinstance(e, dict) or not e.get("file"):
            continue
        flags = set(e.get("flags") or [])
        if flags & {"hidden", "system"}:
            continue
        clean = lambda v: COLOUR.sub("", str(v or "")).strip()
        en, ru = clean(e.get("nameEn")), clean(e.get("name"))
        sw = clean(e.get("speedwalk"))
        route, _ = split_route(sw)
        local = clean(e.get("speedwalk" + suffix)) or sw
        note = split_route(local)[1] if route else local
        parts = split_parts(sw)
        if parts:
            local_parts = split_parts(clean(e.get("speedwalk" + suffix)))
            base = clean(e.get("name" + suffix)) or en or ru
            for i, (label, part_route, _) in enumerate(parts):
                shown = local_parts[i][0] if i < len(local_parts) else label
                out.append({
                    "file": area_key(e["file"]),
                    "name": "%s, %s" % (base, shown),
                    "en": en, "ru": ru,
                    "min": int(e.get("levelLow") or 0),
                    "max": int(e.get("levelHigh") or 0),
                    "levels": bool(e.get("levelHigh")),
                    "route": part_route,
                    "steps": route_steps(part_route),
                    "note": local_parts[i][2] if i < len(local_parts) else parts[i][2],
                    "danger": next((d for d in DANGER if d in flags), ""),
                })
            continue
        out.append({
            "file": area_key(e["file"]),
            "name": clean(e.get("name" + suffix)) or en or ru,
            "en": en,
            "ru": ru,
            "min": int(e.get("levelLow") or 0),
            "max": int(e.get("levelHigh") or 0),
            "levels": bool(e.get("levelHigh")),
            "route": route,
            "steps": route_steps(route) if route else None,
            "note": note,
            "danger": next((d for d in DANGER if d in flags), ""),
        })
    out.sort(key=lambda a: a["name"].lower())
    return out
