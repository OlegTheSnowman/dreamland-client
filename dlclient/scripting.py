"""Triggers, key macros, aliases and variables, kept in step with the web client.

Triggers and macros live on the game server in two lists, the character's own
and the account's, as opaque base64 blobs of JSON (mudjs src/triggers.js and
src/macros.js). The character's aliases are the game's own alias list; the
account's aliases are a blob like the others and are expanded here before a
line is sent (mudjs src/aliases.js). Using the same blobs means a trigger made
in either client shows up in the other.

Nothing in this module touches wx. Callers pass rpc(command, *args) to talk to
the server and later(seconds, fn) to run something after a delay on the UI
thread.
"""

import base64
import json
import re
import time

SCOPES = ("char", "acct")
SAVE_DELAY = 1.2
RETRY_DELAY = 1.5
FLOOD_MAX = 10
FLOOD_WINDOW = 3.0
FLOOD_PAUSE = 10.0
SLOW_SECONDS = 0.15
MAX_TRIGGERS = 200
MAX_MACROS = 300
MAX_ACCT_ALIASES = 300
MAX_LINE = 1023


def b64_encode(obj):
    return base64.b64encode(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii")


def b64_decode(b64):
    if not b64:
        return None
    try:
        return json.loads(base64.b64decode(b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def new_id():
    n = int(time.time() * 1000)
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = digits[r] + s
    import random
    return s + "".join(random.choice(digits) for _ in range(4))


class SyncedLists:
    """Two server-side lists (char, acct) saved shortly after each change."""

    get_cmd = put_cmd = data_cmd = saved_cmd = ""
    max_items = 200

    def __init__(self, rpc, later, on_change=None):
        self.rpc = rpc
        self.later = later
        self.on_change = on_change or (lambda: None)
        self.reset()

    def reset(self):
        self.known = False
        self.account = False
        self.lists = {"char": [], "acct": []}
        self.status = {"char": "idle", "acct": "idle"}
        self.dirty = {"char": False, "acct": False}
        self.gen = {"char": 0, "acct": 0}
        self.asked = False
        self.changed()

    def changed(self):
        self.on_change()

    def valid(self, item):
        return isinstance(item, dict)

    def ask(self):
        if not self.asked and self.rpc(self.get_cmd):
            self.asked = True

    def on_data(self, data):
        if not isinstance(data, dict):
            return
        self.known = True
        self.account = bool(data.get("account"))
        for scope in SCOPES:
            blob = b64_decode((data.get(scope) or {}).get("b64"))
            items = blob.get("list") if isinstance(blob, dict) else None
            self.lists[scope] = [x for x in (items or []) if self.valid(x)]
        self.changed()

    def on_saved(self, data):
        if not isinstance(data, dict) or data.get("scope") not in SCOPES or not self.known:
            return
        scope = data["scope"]
        if data.get("ok"):
            self.status[scope] = "idle"
        elif data.get("reason") == "rate":
            self.dirty[scope] = True
            self._schedule(scope, RETRY_DELAY)
        else:
            self.dirty[scope] = True
            self.status[scope] = "error:" + str(data.get("reason") or "io")
        self.changed()

    def can_edit(self, scope):
        return self.known and (scope == "char" or self.account)

    def set_list(self, scope, items):
        if scope not in SCOPES or not self.can_edit(scope):
            return False
        self.lists[scope] = list(items)[: self.max_items]
        self.dirty[scope] = True
        self._schedule(scope, SAVE_DELAY)
        self.changed()
        return True

    def _schedule(self, scope, delay):
        self.gen[scope] += 1
        g = self.gen[scope]
        self.later(delay, lambda: self._upload(scope, g))

    def _upload(self, scope, g):
        if g != self.gen[scope] or not self.dirty[scope] or not self.known:
            return
        items = self.lists[scope]
        b64 = b64_encode({"v": 1, "list": items}) if items else ""
        if not self.rpc(self.put_cmd, scope, b64):
            self.status[scope] = "error:offline"
        else:
            self.dirty[scope] = False
            self.status[scope] = "saving"
        self.changed()

    def all(self):
        return [(scope, x) for scope in SCOPES for x in self.lists[scope]]


# ----------------------------------------------------------------- triggers
def compile_trigger(trig):
    """A compiled regex for a trigger, or None when it has none."""
    pattern = trig.get("pattern") or ""
    if not pattern:
        return None
    try:
        if trig.get("regex"):
            # JavaScript names groups (?<name>...), Python (?P<name>...).
            return re.compile(re.sub(r"\(\?<(?![=!])", "(?P<", pattern))
        parts = re.split(r"(%[1-9])", pattern)
        out = []
        for i, p in enumerate(parts):
            if re.fullmatch(r"%[1-9]", p):
                at_end = i == len(parts) - 2 and parts[i + 1] == ""
                out.append("(.+)" if at_end else "(.+?)")
            else:
                out.append(re.escape(p))
        return re.compile("".join(out), re.I)
    except re.error:
        return None


def substitute(cmd, m, order):
    def rep(mm):
        n = mm.group(1)
        if n == "0":
            return m.group(0)
        idx = int(n)
        if order is not None:
            if n not in order:
                return ""
            idx = order.index(n) + 1
        try:
            return m.group(idx) or ""
        except IndexError:
            return ""
    return re.sub(r"%([0-9])", rep, cmd)


class Triggers(SyncedLists):
    get_cmd, put_cmd, data_cmd, saved_cmd = "triggers_get", "triggers_put", "triggers_data", "triggers_saved"
    max_items = MAX_TRIGGERS

    def reset(self):
        self.compiled = []
        self.slow = set()
        self.flood = []
        self.flood_until = 0
        super().reset()

    def valid(self, item):
        if not isinstance(item, dict) or not isinstance(item.get("pattern"), str):
            return False
        item.setdefault("id", new_id())
        return True

    def changed(self):
        out = []
        for scope in SCOPES:
            for t in self.lists[scope]:
                if t.get("on") is False or t.get("id") in self.slow:
                    continue
                r = compile_trigger(t)
                if r is None:
                    continue
                order = None if t.get("regex") else [p[1] for p in re.findall(r"%[1-9]", t["pattern"])]
                out.append((t, r, order))
        self.compiled = out
        super().changed()

    def run(self, lines):
        """Match one block of output lines.

        Returns (fired, highlights, notes): fired is [(trigger, command or "", sound)],
        highlights is [(line_index, start, end, mode, colour)], notes are messages
        about triggers switched off for being too slow.
        """
        fired, highlights, notes = [], [], []
        if not self.compiled:
            return fired, highlights, notes
        too_slow = False
        for t, r, order in self.compiled:
            hit = None
            started = time.perf_counter()
            for i, line in enumerate(lines):
                if not line:
                    continue
                m = r.search(line)
                if not m:
                    continue
                hit = hit or m
                hl = t.get("hl")
                if isinstance(hl, dict) and hl.get("color"):
                    if hl.get("mode") == "line":
                        highlights.append((i, 0, len(line), "line", hl["color"]))
                    elif m.end() > m.start():
                        highlights.append((i, m.start(), m.end(), "match", hl["color"]))
            if time.perf_counter() - started > SLOW_SECONDS:
                self.slow.add(t.get("id"))
                too_slow = True
                notes.append(t.get("pattern", ""))
                continue
            if hit:
                cmd = substitute(t.get("cmd") or "", hit, order) if t.get("cmd") else ""
                fired.append((t, cmd, t.get("sound") if isinstance(t.get("sound"), dict) else None))
        if too_slow:
            self.changed()
        return fired, highlights, notes

    def allow_command(self):
        """Flood guard for commands sent by triggers. Returns True, False, or 'paused'."""
        now = time.time()
        if now < self.flood_until:
            return False
        self.flood = [x for x in self.flood if now - x < FLOOD_WINDOW]
        if len(self.flood) >= FLOOD_MAX:
            self.flood_until = now + FLOOD_PAUSE
            self.flood = []
            return "paused"
        self.flood.append(now)
        return True


# ------------------------------------------------------------------- macros
class Macros(SyncedLists):
    get_cmd, put_cmd, data_cmd, saved_cmd = "macros_get", "macros_put", "macros_data", "macros_saved"
    max_items = MAX_MACROS

    def valid(self, item):
        return isinstance(item, dict) and isinstance(item.get("key"), str) and isinstance(item.get("cmd"), str)

    def command_for(self, key):
        for scope in SCOPES:
            for m in self.lists[scope]:
                if m["key"] == key:
                    return m["cmd"]
        return None


# ------------------------------------------------------------------ aliases
class Aliases:
    def __init__(self, rpc, send_line, later, on_change=None):
        self.rpc = rpc
        self.send_line = send_line
        self.later = later
        self.on_change = on_change or (lambda: None)
        self.reset()

    def reset(self):
        self.known = False
        self.max = 1000
        self.account = False
        self.acct_known = False
        self.char = []    # [{"name", "body"}]
        self.acct = []
        self.status = "idle"
        self.dirty = False
        self.gen = 0
        self.asked = False
        self.on_change()

    def ask(self):
        if not self.asked and self.rpc("aliases_get") and self.rpc("aliases_acct_get"):
            self.asked = True

    def on_char(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("aliases"), list):
            return
        self.known = True
        if data.get("max"):
            self.max = data["max"]
        self.char = [{"name": p[0], "body": str(p[1] if len(p) > 1 else "")}
                     for p in data["aliases"] if isinstance(p, list) and p and isinstance(p[0], str)]
        self.on_change()

    def on_acct(self, data):
        if not isinstance(data, dict):
            return
        self.acct_known = True
        self.account = bool(data.get("account"))
        blob = b64_decode(data.get("b64"))
        items = blob.get("list") if isinstance(blob, dict) else None
        self.acct = [x for x in (items or [])
                     if isinstance(x, dict) and isinstance(x.get("name"), str) and isinstance(x.get("body"), str)]
        self.on_change()

    def on_saved(self, data):
        if not isinstance(data, dict) or not self.acct_known:
            return
        if data.get("ok"):
            self.status = "idle"
        elif data.get("reason") == "rate":
            self.dirty = True
            self._schedule(RETRY_DELAY)
        else:
            self.dirty = True
            self.status = "error:" + str(data.get("reason") or "io")
        self.on_change()

    @staticmethod
    def bad_name(name):
        if not name:
            return "empty"
        if re.search(r"\s", name):
            return "space"
        if name[0] in "'\"":
            return "quote"
        if "|" in name:
            return "pipe"
        if name.lower() == "flush":
            return "flush"
        return ""

    # The character's list is the game's own: change it with game commands.
    def set_char(self, old_name, name, body):
        if old_name and old_name != name:
            self.send_line("unalias " + old_name)
        self.send_line("alias %s %s" % (name, body.replace("|", "||")))

    def remove_char(self, name):
        self.send_line("unalias " + name)

    def set_acct(self, items):
        if not self.acct_known or not self.account:
            return False
        self.acct = list(items)[:MAX_ACCT_ALIASES]
        self.dirty = True
        self._schedule(SAVE_DELAY)
        self.on_change()
        return True

    def _schedule(self, delay):
        self.gen += 1
        g = self.gen
        self.later(delay, lambda: self._upload(g))

    def _upload(self, g):
        if g != self.gen or not self.dirty or not self.acct_known:
            return
        b64 = b64_encode({"v": 1, "list": self.acct}) if self.acct else ""
        if not self.rpc("aliases_acct_put", b64):
            self.status = "error:offline"
        else:
            self.dirty = False
            self.status = "saving"
        self.on_change()

    def expand(self, line):
        """Expand account aliases in a line, the way the game expands its own."""
        if not self.acct or line is None:
            return line
        pieces, cur, i = [], "", 0
        while i < len(line):
            c = line[i]
            if c == "|":
                if i + 1 < len(line) and line[i + 1] == "|":
                    cur += "||"
                    i += 2
                    continue
                pieces.append(cur)
                cur = ""
            else:
                cur += c
            i += 1
        pieces.append(cur)
        return "|".join(self._expand_piece(p) for p in pieces)

    def _expand_piece(self, piece):
        m = re.match(r"^(\s*)(\S+)(.*)$", piece, re.S)
        if not m:
            return piece
        word = m.group(2)
        if word[0] in "'\"":
            return piece
        if any(a["name"] == word for a in self.char):
            return piece
        hit = next((a for a in self.acct if a["name"] == word), None)
        if not hit:
            return piece
        rest = m.group(3).strip()
        return hit["body"] + (" " + rest if rest else "")


# ---------------------------------------------------------------- variables
VAR_NAME = re.compile(r"^[a-zA-Zа-яА-ЯёЁіІїЇєЄґҐ][\wа-яА-ЯёЁіІїЇєЄґҐ]*$")


def expand_vars(text, variables):
    """Put #var values in place of $name, as mudjs parseUserVars does."""
    if "$" not in text or not variables:
        return text
    return re.sub(r"\$([\wа-яА-ЯёЁіІїЇєЄґҐ]+)",
                  lambda m: variables.get(m.group(1), m.group(0)) if variables.get(m.group(1)) else m.group(0),
                  text)


# ---------------------------------------------------------------- key names
# Names follow mudjs keycode.js, so a macro made in the browser fires here:
# modifiers in the order ctrl, alt, shift, then the key: "f1", "alt+kp2".
_VK_NAMES = {27: "esc", 32: "space", 33: "pgup", 34: "pgdn", 35: "end", 36: "home", 37: "left",
             38: "up", 39: "right", 40: "down", 45: "ins", 46: "del", 106: "kp*", 107: "kp+",
             109: "kp-", 110: "kp.", 111: "kp/", 186: ";", 187: "=", 188: ",", 189: "-", 190: ".",
             191: "/", 192: "`", 219: "[", 220: "\\", 221: "]", 222: "'"}
for _i in range(65, 91):
    _VK_NAMES[_i] = chr(_i + 32)
for _i in range(48, 58):
    _VK_NAMES[_i] = chr(_i)
for _i in range(1, 13):
    _VK_NAMES[111 + _i] = "f%d" % _i
for _i in range(10):
    _VK_NAMES[96 + _i] = "kp%d" % _i

KEY_NAMES = set(_VK_NAMES.values())
MODIFIERS = ("ctrl", "alt", "shift")

# Cyrillic letters sit on the same physical keys as these Latin ones.
_CYRILLIC = {
    "й": "q", "ц": "w", "у": "e", "к": "r", "е": "t", "н": "y", "г": "u", "ш": "i", "щ": "o", "з": "p",
    "х": "[", "ъ": "]", "ї": "]", "ф": "a", "ы": "s", "і": "s", "в": "d", "а": "f", "п": "g", "р": "h",
    "о": "j", "л": "k", "д": "l", "ж": ";", "э": "'", "є": "'", "я": "z", "ч": "x", "с": "c", "м": "v",
    "и": "b", "т": "n", "ь": "m", "б": ",", "ю": ".", "ё": "`", "ґ": "\\",
}
_ALIASES = {"pgdown": "pgdn", "escape": "esc", "insert": "ins", "delete": "del"}


def key_name(vk, numpad=None, ctrl=False, alt=False, shift=False):
    """Name of a key press from its Windows virtual key code.

    numpad is the keypad name ("kp2") when the press came from the keypad,
    whatever NumLock says; then that name wins over the arrow the VK reports.
    """
    key = numpad or _VK_NAMES.get(vk)
    if not key:
        return None
    mods = [m for m, on in (("ctrl", ctrl), ("alt", alt), ("shift", shift)) if on]
    return "+".join(mods + [key])


def canonical_key(raw):
    """Any spelling of a combination ("Shift+Ctrl+я") as key_name would give it, or ""."""
    parts = re.sub(r"\s", "", str(raw).lower()).split("+")
    if len(parts) > 1 and parts[-1] == "" and parts[-2] == "kp":
        parts.pop()
        parts[-1] = "kp+"
    last = parts.pop()
    last = _ALIASES.get(last, last)
    last = _CYRILLIC.get(last, last)
    if last not in KEY_NAMES:
        return ""
    if any(p not in MODIFIERS for p in parts):
        return ""
    return "+".join([m for m in MODIFIERS if m in parts] + [last])
