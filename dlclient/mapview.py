import re

COLOUR = re.compile(r"\{.")
REVERSE = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
DELTA = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}
DIR_ORDER = ["north", "east", "south", "west", "up", "down"]

SECTOR_COLOUR = {
    "inside": "#d9b94a", "city": "#ffffff", "field": "#8ee34f", "forest": "#6cba2e", "hills": "#c4a000",
    "mountain": "#a7aaa3", "water_swim": "#55a3f2", "water_noswim": "#4a86d8", "underwater": "#5a90d0",
    "air": "#7fc0ff", "desert": "#fdea56", "cave": "#a7aaa3", "jungle": "#45c9b0", "tundra": "#e6e9e1",
    "unknown": "#a7aaa3",
}


def _name(room, lang):
    name = room.get("name") or ""
    if lang != "ru":
        name = ((room.get("i18n") or {}).get(lang) or {}).get("name") or name
    return COLOUR.sub("", name).strip()


class AreaMap:
    def __init__(self, graph, lang, area_names=None):
        self.lang = lang
        meta = graph.get("meta") or {}
        self.name = (((meta.get("i18n") or {}).get(lang) or {}).get("name") if lang != "ru" else None) \
            or meta.get("name") or meta.get("file") or ""
        self.area_names = area_names or {}
        rooms = graph.get("rooms") or {}
        rooms = rooms.values() if isinstance(rooms, dict) else rooms
        placed = graph.get("placed") or {}
        if isinstance(placed, list):
            placed = {str(p.get("vnum")): p for p in placed}
        styles = {}
        for e in graph.get("exits") or []:
            try:
                key = (int(e["from"]), e["dir"])
            except (KeyError, TypeError, ValueError):
                continue
            styles[key] = e
            if e.get("bidirectional") and e.get("style") != "cross_area" and e.get("dir") in REVERSE:
                styles.setdefault((int(e["to"]), REVERSE[e["dir"]]), e)
        self.rooms = {}
        for room in rooms:
            if not isinstance(room, dict) or "vnum" not in room:
                continue
            vnum = int(room["vnum"])
            pos = placed.get(str(vnum))
            if not pos:
                continue
            exits = []
            for ex in room.get("exits") or []:
                d = ex.get("dir")
                if d not in REVERSE:
                    continue
                info = styles.get((vnum, d)) or {}
                style = info.get("style") or "open"
                exits.append({"dir": d, "to": int(ex.get("target") or 0), "style": style,
                              "area": info.get("targetArea") or "", "door": info.get("doorKeyword") or ""})
            exits.sort(key=lambda x: DIR_ORDER.index(x["dir"]))
            self.rooms[vnum] = {"vnum": vnum, "name": _name(room, lang), "sector": room.get("sector") or "unknown",
                                "x": int(pos.get("x", 0)), "y": int(pos.get("y", 0)), "z": int(pos.get("z", 0)),
                                "exits": exits}
        for r in self.rooms.values():
            for ex in r["exits"]:
                if ex["style"] != "cross_area" and ex["to"] not in self.rooms:
                    ex["style"] = "cross_area"
        self.levels = sorted({r["z"] for r in self.rooms.values()})

    def start(self, vnum):
        if vnum in self.rooms:
            return vnum
        if not self.rooms:
            return None
        return min(self.rooms, key=lambda v: (abs(self.rooms[v]["z"]), v))

    def exit_to(self, vnum, direction):
        for ex in self.rooms[vnum]["exits"]:
            if ex["dir"] == direction and ex["to"] in self.rooms and ex["style"] != "cross_area":
                return ex["to"]
        return None

    def step(self, vnum, direction):
        linked = self.exit_to(vnum, direction)
        if linked is not None:
            return linked
        here = self.rooms[vnum]
        if direction in ("up", "down"):
            want = here["z"] + (1 if direction == "up" else -1)
            same = [r for r in self.rooms.values() if r["z"] == want]
            if not same:
                return None
            return min(same, key=lambda r: ((r["x"] - here["x"]) ** 2 + (r["y"] - here["y"]) ** 2, r["vnum"]))["vnum"]
        dx, dy = DELTA[direction]
        best, best_score = None, None
        for r in self.rooms.values():
            if r["z"] != here["z"] or r["vnum"] == vnum:
                continue
            ox, oy = r["x"] - here["x"], r["y"] - here["y"]
            along = ox * dx + oy * dy
            if along <= 0:
                continue
            across = abs(ox * dy - oy * dx)
            if across > along * 2:
                continue
            score = along + across * 2.5
            if best_score is None or score < best_score:
                best, best_score = r["vnum"], score
        return best

    def steps_from(self, here):
        if getattr(self, "_steps_for", None) == here:
            return self._steps
        dist = {here: 0} if here in self.rooms else {}
        queue = [here] if dist else []
        while queue:
            cur = queue.pop(0)
            for ex in self.rooms[cur]["exits"]:
                t = ex["to"]
                if t in self.rooms and t not in dist and ex["style"] != "cross_area":
                    dist[t] = dist[cur] + 1
                    queue.append(t)
        self._steps_for, self._steps = here, dist
        return dist

    def offset(self, vnum, here):
        a, b = self.rooms.get(vnum), self.rooms.get(here)
        if not a or not b:
            return None
        return a["x"] - b["x"], a["y"] - b["y"], a["z"] - b["z"]

    def area_name(self, key):
        return self.area_names.get(key) or key


def describe(amap, vnum, here, tr):
    r = amap.rooms[vnum]
    key = "map.sector." + r["sector"]
    sector = tr(key)
    parts = [r["name"] or str(vnum), r["sector"] if sector == key else sector]
    if vnum == here:
        parts.append(tr("map.here"))
    else:
        off = amap.offset(vnum, here)
        if off:
            dx, dy, dz = off
            pieces = []
            if dx or dy:
                ns = "n" if dy > 0 else "s"
                ew = "e" if dx > 0 else "w"
                if abs(dx) * 2 < abs(dy):
                    compass = ns
                elif abs(dy) * 2 < abs(dx):
                    compass = ew
                else:
                    compass = ns + ew
                pieces.append(tr("map.where", tr("compass." + compass)))
            if dz:
                pieces.append(tr("map.u" if dz > 0 else "map.d", abs(dz)))
            steps = amap.steps_from(here).get(vnum) if here is not None else None
            if steps:
                pieces.append(tr("map.step1") if steps == 1 else tr("map.steps", steps))
            if pieces:
                parts.append(", ".join(pieces))
    exits = []
    for ex in r["exits"]:
        d = tr("dir." + ex["dir"])
        if ex["style"] == "cross_area":
            exits.append(tr("map.leads", d, amap.area_name(ex["area"])) if ex["area"] else d)
        elif ex["style"] in ("door_closed", "door_locked", "door_pickproof", "warp", "random"):
            exits.append("%s %s" % (d, tr("map.exit." + ex["style"])))
        else:
            exits.append(d)
    parts.append(tr("map.exits", ", ".join(exits)) if exits else tr("map.noexits"))
    return ". ".join(p for p in parts if p) + "."


def colour_for(sector):
    return SECTOR_COLOUR.get(sector, SECTOR_COLOUR["unknown"])

