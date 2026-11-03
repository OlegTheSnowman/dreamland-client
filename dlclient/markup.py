"""Turn the server's console_out text into plain text plus clickable commands.

The web branch of the server sends its own small markup inside the text:

  <c c='fgbr'>...</c>          colour, dropped here
  <hc>look</hc>                send the label as a command
  <hc cmd='path 3001'>Name</hc> send cmd instead, only for allowlisted shapes
  <hh>topic</hh>, <hh id='n'>  help article
  <hg>group</hg>               skill group list
  <hs>2n3e</hs>                speedwalk
  <hl>http://...</hl>          web link
  <m i='id' c='take $,..' l='..'>item</m>  item with a command menu
  [read=..,see=..] [look=..,see=..] [cmd=..,see=..,nonce=..] [map=x.are]

Everything else is ordinary text with &lt; &gt; &amp; escaped. This follows
mudjs src/manip.js, including its safety rules: an <hc cmd=...> outside the
allowlist sends its label, and a [cmd=] without this connection's nonce is
shown as plain text.
"""

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
    if value and any(r.match(value) for r in SAFE_HC_COMMANDS):
        return value
    return None


@dataclass
class Link:
    """A clickable piece of a line. start and end are character offsets in it."""
    start: int
    end: int
    label: str
    command: str = ""          # sent on activation; empty for web links
    url: str = ""              # web link to open in the browser
    menu: list = field(default_factory=list)   # item menu: [(label, command)], None = divider
    confirm: bool = False      # ask before sending (starting a craft uses up items)


@dataclass
class Line:
    text: str
    links: list


def _attr_escape(s):
    return html.escape(s, quote=True)


def _brackets_to_tags(s, nonce):
    """Rewrite the [..] placeholders as tags the parser below understands."""
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


class _Parser(HTMLParser):
    LINK_TAGS = {"hc", "hh", "hg", "hs", "hl", "m", "x"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.pos = 0
        self.links = []
        self.stack = []   # open link tags: (tag, attrs, start, collected text)

    def handle_starttag(self, tag, attrs):
        if tag in self.LINK_TAGS:
            self.stack.append((tag, dict(attrs), self.pos, []))

    def handle_startendtag(self, tag, attrs):
        pass  # <c c='x'/> style colour resets carry no text

    def handle_endtag(self, tag):
        if tag not in self.LINK_TAGS:
            return
        # Close the innermost matching tag; ignore a stray end tag.
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
        # Underline only the words, not the padding around them.
        lead = len(label) - len(label.lstrip())
        s, e = start + lead, start + lead + len(stripped)
        link = Link(s, e, stripped)
        if tag == "hc":
            explicit = safe_explicit_action(attrs.get("cmd"))
            link.command = explicit or stripped
            link.confirm = bool(explicit and re.match(r"^craft \d+$", explicit))
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
        self.links.append(link)


class OutputParser:
    """Stateful: holds the partial line between frames."""

    def __init__(self):
        self.nonce = None
        self.msp_enabled = False

    def parse(self, raw):
        """Return (lines, msp) for one console_out payload.

        lines is a list of Line; the last one may be a prompt with no newline.
        msp is a list of (kind, name, opts) to play.
        """
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
        # Tags left open at the end of a frame still count up to there.
        while p.stack:
            t, attrs, start, parts = p.stack.pop()
            p._finish(t, attrs, start, "".join(parts))
        text = "".join(p.text).replace("\xa0", " ")

        lines = []
        offset = 0
        for chunk in text.split("\n"):
            end = offset + len(chunk)
            links = [Link(l.start - offset, l.end - offset, l.label, l.command, l.url, l.menu, l.confirm)
                     for l in p.links if l.start >= offset and l.end <= end]
            lines.append(Line(chunk, sorted(links, key=lambda l: l.start)))
            offset = end + 1
        # A frame that ends with a newline leaves an empty last piece: drop it so
        # callers know the frame ended on a complete line.
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
