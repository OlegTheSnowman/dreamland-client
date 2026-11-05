import re

COLOUR = re.compile(r"\{.")
REVERSE = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
DELTA = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}
DIR_ORDER = ["north", "east", "south", "west", "up", "down"]



def _desc(room, lang):
    desc = room.get("description") or ""
    if lang != "ru":
        desc = ((room.get("i18n") or {}).get(lang) or {}).get("description") or desc
    return COLOUR.sub("", desc).strip()


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
            self.rooms[vnum] = {"vnum": vnum, "name": _name(room, lang), "desc": _desc(room, lang),
                                "sector": room.get("sector") or "unknown",
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

