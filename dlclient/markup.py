import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

SAFE_HC_COMMANDS = [
    re.compile(r"^path \d{1,7}$"),
    re.compile(r"^vault (\*[a-z0-9]{1,20} )?(get \d{1,5}|filter [a-z_]{1,20})$", re.I),
    re.compile(r"^account switch [A-Za-z]{1,20}$"),
    re.compile(r"^craft (show )?\d{1,7}$"),
    re.compile(r"^craft filter [a-z]{1,12}$"),
]

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
MSP_RE = re.compile(r"^!!(SOUND|MUSIC)\(([^)\n]*)\)[ \t]*$")


def safe_explicit_action(value):
    if value and any(r.fullmatch(value) for r in SAFE_HC_COMMANDS):
        return value
    return None


@dataclass
class Link:
    start: int
    end: int
    label: str
    command: str = ""
    url: str = ""
    menu: list = field(default_factory=list)
    confirm: bool = False
    ident: str = ""


@dataclass
class Line:
    text: str
    links: list
    colors: list = field(default_factory=list)



def _attr_escape(s):
    return html.escape(s, quote=True)


def _brackets_to_tags(s, nonce):
    s = re.sub(r"\[map=([-0-9a-z_]{1,15})\.are\]",
               lambda m: "<hl>https://dreamland.rocks/maps.html#%s</hl>" % m.group(1), s)

    def read(m):
        what, see = m.group(1), m.group(2)
        if see.lower() not in what.lower().split(" "):
            return ""
        return "<x cmd='%s'>%s</x>" % (_attr_escape("examine '%s'" % html.unescape(what)), see)

    s = re.sub(r"\[read=([^,]{1,200}),see=([^\]]{1,30})\]", read, s, flags=re.I)
    s = re.sub(r"\[look=([^,]{1,200}),see=([^\]]{1,30})\]",
               lambda m: "<x cmd='%s'>%s</x>" % (_attr_escape("look " + html.unescape(m.group(1))), m.group(2)),
               s, flags=re.I)

    def cmd(m):
        command, see, n = m.group(1), m.group(2), m.group(3)
        if not nonce or n != nonce:
            return m.group(0)
        action = html.unescape(command).replace("$1", html.unescape(see.strip(" ")), 1)
        stripped = see.strip(" ")
        lead = see[:len(see) - len(see.lstrip(" "))]
        trail = see[len(see.rstrip(" ")):]
        return "%s<x cmd='%s'>%s</x>%s" % (lead, _attr_escape(action), stripped, trail)

    s = re.sub(r"\[cmd=([^,]{1,200}),see=([^\]]{1,50}),nonce=(.{8})\]", cmd, s, flags=re.I)
    return s


LOOK_HINT = re.compile(r"^(?:You can look at|Можна подивитися|Можно посмотреть): [^.]*\.(?=\s*\S)")


def split_look_hint(line):
    m = LOOK_HINT.match(line.text)
    if not m:
        return [line]
    cut = m.end()
    rest = len(line.text) - len(line.text[cut:].lstrip())
    first = Line(line.text[:cut], [l for l in line.links if l.end <= cut],
                 [(a, min(b, cut), c) for a, b, c in line.colors if a < cut])
    moved = [Link(l.start - rest, l.end - rest, l.label, l.command, l.url, l.menu, l.confirm, l.ident)
             for l in line.links if l.start >= rest]
    second = Line(line.text[rest:], moved, [(max(a, rest) - rest, b - rest, c) for a, b, c in line.colors if b > rest])
    return [first, second]


class _Parser(HTMLParser):
    LINK_TAGS = {"hc", "hh", "hg", "hs", "hl", "m", "x"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.pos = 0
        self.links = []
        self.stack = []
        self.colors = []
        self.color_stack = []

    def handle_starttag(self, tag, attrs):
        if tag == "c":
            self.color_stack.append((dict(attrs).get("c") or "", self.pos))
            return
        if tag in self.LINK_TAGS:
            self.stack.append((tag, dict(attrs), self.pos, []))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag == "c":
            if self.color_stack:
                cls, start = self.color_stack.pop()
                if cls and self.pos > start:
                    self.colors.append((start, self.pos, cls))
            return
        if tag not in self.LINK_TAGS:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                t, attrs, start, parts = self.stack.pop(i)
                self._finish(t, attrs, start, "".join(parts))
                return

    def handle_data(self, data):
        self.text.append(data)
        self.pos += len(data)
        for item in self.stack:
            item[3].append(data)

    def _finish(self, tag, attrs, start, inner):
        label = inner
        stripped = label.strip()
        if not stripped:
            return
        lead = len(label) - len(label.lstrip())
        s, e = start + lead, start + lead + len(stripped)
        link = Link(s, e, stripped)
        if tag == "hc":
            explicit = safe_explicit_action(attrs.get("cmd"))
            link.command = explicit or stripped
            link.confirm = bool(explicit and re.fullmatch(r"craft \d+", explicit))
        elif tag == "hh":
            link.command = "help " + (attrs.get("id") or stripped)
        elif tag == "hg":
            link.command = "glist " + stripped
        elif tag == "hs":
            link.command = "run " + stripped
        elif tag == "hl":
            if not stripped.startswith("http"):
                return
            link.url = stripped
        elif tag == "x":
            link.command = attrs.get("cmd", stripped)
        elif tag == "m":
            ident = attrs.get("i", "")
            menu = []

            def add(cmd):
                if not cmd.strip():
                    return
                action = cmd.replace("$", ident, 1)
                shown = re.sub(r"( *\$ *| *[0-9]{5,}|\.'.*')", "", cmd).strip()
                menu.append((shown or action, action))

            for c in (attrs.get("c") or "").split(","):
                add(c)
            if attrs.get("l"):
                menu.append(None)
                for c in attrs["l"].split(","):
                    add(c)
            if not [m for m in menu if m]:
                return
            link.menu = menu
            link.ident = ident
        self.links.append(link)


class OutputParser:
    def __init__(self):
        self.nonce = None
        self.msp_enabled = False

    def parse(self, raw):
        raw = ANSI_RE.sub("", raw).replace("\r", "")
        msp = []
        if self.msp_enabled and "!!" in raw:
            kept = []
            for piece in raw.split("\n"):
                m = MSP_RE.match(piece.strip())
                if m:
                    msp.append(_msp_parse(m))
                else:
                    kept.append(piece)
            raw = "\n".join(kept)

        p = _Parser()
        p.feed(_brackets_to_tags(raw, self.nonce))
        p.close()
        while p.stack:
            t, attrs, start, parts = p.stack.pop()
            p._finish(t, attrs, start, "".join(parts))
        while p.color_stack:
            cls, start = p.color_stack.pop()
            if cls and p.pos > start:
                p.colors.append((start, p.pos, cls))
        p.colors.sort(key=lambda c: -(c[1] - c[0]))
        text = "".join(p.text).replace("\xa0", " ")

        lines = []
        offset = 0
        for chunk in text.split("\n"):
            end = offset + len(chunk)
            links = [Link(l.start - offset, l.end - offset, l.label, l.command, l.url, l.menu, l.confirm, l.ident)
                     for l in p.links if l.start >= offset and l.end <= end]
            colors = [(max(a, offset) - offset, min(b, end) - offset, c)
                      for a, b, c in p.colors if a < end and b > offset]
            lines.extend(split_look_hint(Line(chunk, sorted(links, key=lambda l: l.start), colors)))
            offset = end + 1
        complete = text.endswith("\n")
        if complete:
            lines.pop()
        return lines, complete, msp


def _msp_parse(m):
    parts = m.group(2).strip().split()
    name = parts.pop(0) if parts else ""
    opts = {}
    for part in parts:
        kv = re.match(r"^([A-Z])=(\S*)$", part)
        if kv:
            opts[kv.group(1)] = kv.group(2)
    return (m.group(1).lower(), name, opts)
