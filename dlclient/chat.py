"""Chat buffers: the channel messages the server sends apart from the game text.

After chat_subscribe the server sends every channel line again as a 'chat'
frame (plug-ins/output/chatframe.cpp): the channel id (ooc, gossip, cb...),
its kind (world, personal, group, room, mob), whether it came in or went out,
and the text exactly as the console printed it. The web client keeps them in
its chat panel; here they go into buffers the player walks with the keyboard.

History is kept per character, on this computer, one JSON line per message in
%APPDATA%\\DreamLandClient\\chat\\<name>.jsonl, like the web client's archive.
"""

import json
import os
import re
import time

KEEP_IN_MEMORY = 3000
ALL = "all"
KIND_BUFFERS = {"personal": "tells", "group": "group", "room": "room", "mob": "mob"}


def buffer_of(row):
    """The buffer a message belongs to besides 'all'."""
    kind = row.get("kind") or "world"
    if kind in KIND_BUFFERS:
        return KIND_BUFFERS[kind]
    return row.get("chan") or "other"


class ChatStore:
    def __init__(self, folder, to_text):
        self.folder = folder
        self.to_text = to_text        # markup -> plain text, the console's parser
        self.who = None
        self.rows = []                # oldest first
        self.order = [ALL]            # buffers in the order they first appeared
        self.current = ALL
        self.pos = {}                 # buffer -> index into its rows, None = past the newest

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
        """A chat frame. Returns the stored row, or None when no one is playing."""
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
        """Walk the current buffer. Returns (row, edge) where edge is 'top', 'end' or None."""
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
