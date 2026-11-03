"""Telnet commands inside console_out text.

The server sends telnet bytes as their KOI8-R letters (see mudjs src/telnet.js),
so IAC is the letter Ъ. A doubled IAC is a literal Ъ. The only option the
client acts on is ECHO: WILL ECHO means the server hides what we type (a
password), WONT ECHO means it is shown again.
"""

IAC = "Ъ"   # Ъ  255
DONT = "Ч"  # Ч  254
DO = "Щ"    # Щ  253
WONT = "Э"  # Э  252
WILL = "Ш"  # Ш  251
SB = "З"    # З  250
SE = "П"    # П  240
ECHO = "\x01"

NORMAL, GOT_IAC, SUBNEG, SUBNEG_IAC = range(4)


class Telnet:
    def __init__(self):
        self.state = NORMAL
        self.verb = None
        self.echo_off = False   # True while the server hides our input

    def process(self, s):
        out = []
        for ch in s:
            st = self.state
            if st == NORMAL:
                if ch == IAC:
                    self.state = GOT_IAC
                else:
                    out.append(ch)
            elif st == GOT_IAC:
                if ch in (DONT, DO, WONT, WILL):
                    self.verb = ch
                    self.state = "opt"
                elif ch == SB:
                    self.state = SUBNEG
                elif ch == IAC:
                    out.append(ch)
                    self.state = NORMAL
                else:
                    self.state = NORMAL
            elif st == "opt":
                if ch == ECHO and self.verb == WILL:
                    self.echo_off = True
                elif ch == ECHO and self.verb == WONT:
                    self.echo_off = False
                self.state = NORMAL
            elif st == SUBNEG:
                if ch == IAC:
                    self.state = SUBNEG_IAC
            elif st == SUBNEG_IAC:
                self.state = NORMAL if ch == SE else SUBNEG
        return "".join(out)
