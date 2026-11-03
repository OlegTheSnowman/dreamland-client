import json
import os
import re
import time

KEEP_IN_MEMORY = 3000
ALL = "all"
KIND_BUFFERS = {"personal": "tells", "group": "group", "room": "room", "mob": "mob"}


def buffer_of(row):
    kind = row.get("kind") or "world"
    if kind in KIND_BUFFERS:
        return KIND_BUFFERS[kind]
    return row.get("chan") or "other"


class ChatStore:
    def __init__(self, folder, to_text):
        self.folder = folder
        self.to_text = to_text
        self.who = None
        self.rows = []
        self.order = [ALL]
        self.current = ALL
        self.pos = {}

    def _path(self, who):
        safe = re.sub(r"[^\w-]", "_", who.lower())
        return os.path.join(self.folder, safe + ".jsonl")

    def set_who(self, who):
        if who == self.who:
            return
        self.who = who
        self.rows = []
        self.order = [ALL]
        self.current = ALL
        self.pos = {}
        if not who:
            return
        try:
            with open(self._path(who), encoding="utf-8") as f:
                lines = f.readlines()[-KEEP_IN_MEMORY:]
        except OSError:
            lines = []
        for line in lines:
            try:
                self._remember(json.loads(line))
            except ValueError:
                continue

    def _remember(self, row):
        self.rows.append(row)
        if len(self.rows) > KEEP_IN_MEMORY:
            del self.rows[: len(self.rows) - KEEP_IN_MEMORY]
        b = buffer_of(row)
        if b not in self.order:
            self.order.append(b)

    def add(self, body):
        if not self.who or not isinstance(body, dict):
            return None
        peer = body.get("peer") or {}
        row = {
            "at": body.get("at") or int(time.time()),
            "chan": body.get("id") or "",
            "kind": body.get("kind") or "world",
            "dir": body.get("dir") or "in",
            "text": self.to_text(str(body.get("text") or "")),
            "name": peer.get("name") or "",
        }
        self._remember(row)
        try:
            os.makedirs(self.folder, exist_ok=True)
            with open(self._path(self.who), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return row

    def buffer_rows(self, name=None):
        name = name or self.current
        if name == ALL:
            return self.rows
        return [r for r in self.rows if buffer_of(r) == name]

    def switch(self, step):
        i = (self.order.index(self.current) + step) % len(self.order)
        self.current = self.order[i]
        return self.current

    def move(self, step):
        rows = self.buffer_rows()
        if not rows:
            return None, "empty"
        pos = self.pos.get(self.current)
        if pos is None:
            pos = len(rows)
        pos += step
        if pos < 0:
            self.pos[self.current] = 0
            return rows[0], "top"
        if pos >= len(rows):
            self.pos[self.current] = len(rows) - 1
            return rows[-1], "end"
        self.pos[self.current] = pos
        return rows[pos], None

    def newest(self):
        rows = self.buffer_rows()
        if not rows:
            return None
        self.pos[self.current] = len(rows) - 1
        return rows[-1]
