import wx

from .access import NamedAccessible
from .mapview import colour_for, describe

CELL_W, CELL_H = 170, 70
BOX_W, BOX_H = 150, 40
KEY_DIRS = {wx.WXK_UP: "north", wx.WXK_DOWN: "south", wx.WXK_LEFT: "west", wx.WXK_RIGHT: "east",
            wx.WXK_NUMPAD_UP: "north", wx.WXK_NUMPAD_DOWN: "south", wx.WXK_NUMPAD_LEFT: "west",
            wx.WXK_NUMPAD_RIGHT: "east", wx.WXK_PAGEUP: "up", wx.WXK_PAGEDOWN: "down",
            wx.WXK_NUMPAD_PAGEUP: "up", wx.WXK_NUMPAD_PAGEDOWN: "down"}
STEP = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}


class MapCanvas(wx.Window):
    def __init__(self, parent, dialog):
        super().__init__(parent, style=wx.WANTS_CHARS | wx.FULL_REPAINT_ON_RESIZE | wx.BORDER_NONE)
        self.dialog = dialog
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((640, 420))
        self.acc = NamedAccessible(self, dialog.tr("map.canvas"))
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_KEY_DOWN, dialog.on_key)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_click)
        self.Bind(wx.EVT_LEFT_DCLICK, lambda e: dialog.walk())

    def to_screen(self, r, size=None):
        sel = self.dialog.amap.rooms[self.dialog.sel]
        w, h = size or self.GetClientSize()
        x = w // 2 + (r["x"] - sel["x"]) * CELL_W
        y = h // 2 - (r["y"] - sel["y"]) * CELL_H
        return x, y

    def on_click(self, event):
        d = self.dialog
        z = d.amap.rooms[d.sel]["z"]
        for r in d.amap.rooms.values():
            if r["z"] != z:
                continue
            x, y = self.to_screen(r)
            if abs(event.GetX() - x) <= BOX_W // 2 and abs(event.GetY() - y) <= BOX_H // 2:
                d.select(r["vnum"])
                break
        self.SetFocus()

    def on_paint(self, event):
        self.draw(wx.AutoBufferedPaintDC(self), self.GetClientSize())

    def draw(self, dc, size):
        d = self.dialog
        dc.SetBackground(wx.Brush(wx.Colour("#0d0b12")))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if not gc:
            return
        rooms = d.amap.rooms
        z = rooms[d.sel]["z"]
        w, h = size
        font = self.GetFont()
        for r in rooms.values():
            if r["z"] != z:
                continue
            x, y = self.to_screen(r, size)
            if x < -CELL_W or x > w + CELL_W or y < -CELL_H or y > h + CELL_H:
                continue
            for ex in r["exits"]:
                if ex["dir"] not in STEP:
                    continue
                target = rooms.get(ex["to"])
                colour = "#06989a" if ex["style"] == "cross_area" else (
                    "#cc0000" if ex["style"] in ("door_locked", "door_pickproof") else
                    "#d384cb" if ex["style"] == "warp" else "#888888")
                pen = wx.Pen(wx.Colour(colour), 2, wx.PENSTYLE_SHORT_DASH if ex["style"] not in ("open",) else wx.PENSTYLE_SOLID)
                gc.SetPen(pen)
                if target and target["z"] == z and ex["style"] != "cross_area":
                    tx, ty = self.to_screen(target, size)
                else:
                    sx, sy = STEP[ex["dir"]]
                    tx, ty = x + sx * CELL_W // 2, y - sy * CELL_H // 2
                gc.StrokeLine(x, y, tx, ty)
        for r in rooms.values():
            if r["z"] != z:
                continue
            x, y = self.to_screen(r, size)
            if x < -CELL_W or x > w + CELL_W or y < -CELL_H or y > h + CELL_H:
                continue
            selected = r["vnum"] == d.sel
            here = r["vnum"] == d.here
            gc.SetBrush(wx.Brush(wx.Colour("#3a2f55" if selected else "#16131f")))
            gc.SetPen(wx.Pen(wx.Colour("#bb86fc" if selected else ("#ffd700" if here else "#2b2638")),
                             3 if selected or here else 1))
            gc.DrawRoundedRectangle(x - BOX_W // 2, y - BOX_H // 2, BOX_W, BOX_H, 6)
            gc.SetFont(font, wx.Colour(colour_for(r["sector"])))
            label = r["name"] if len(r["name"]) <= 20 else r["name"][:19] + "."
            tw, th = gc.GetTextExtent(label)[:2]
            gc.DrawText(label, x - tw / 2, y - th / 2)
        gc.SetFont(font, wx.Colour("#e3d8c0"))
        title = "%s  %s" % (d.amap.name, d.tr("map.level", z))
        gc.DrawText(title, 10, 8)


class MapDialog(wx.Dialog):
    def __init__(self, parent, tr, amap, here, say):
        super().__init__(parent, title=tr("map.title", amap.name), size=(900, 640),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
        self.tr, self.amap, self.say = tr, amap, say
        self.here = here if here in amap.rooms else None
        self.sel = amap.start(here)
        self.choice = None
        s = wx.BoxSizer(wx.VERTICAL)
        self.canvas = MapCanvas(self, self)
        s.Add(self.canvas, 1, wx.EXPAND)
        close = wx.Button(self, wx.ID_CANCEL, tr("list.close"))
        s.Add(close, 0, wx.ALL | wx.ALIGN_RIGHT, 6)
        self.SetSizer(s)
        self.canvas.SetFocus()
        self.update_name()
        wx.CallLater(150, lambda: self.say(tr("map.intro", amap.name) + " " + self.text()))

    def text(self):
        return describe(self.amap, self.sel, self.here, self.tr)

    def update_name(self):
        self.canvas.acc.name = self.text()

    def select(self, vnum, extra=""):
        old_z = self.amap.rooms[self.sel]["z"]
        self.sel = vnum
        self.update_name()
        self.canvas.Refresh()
        z = self.amap.rooms[vnum]["z"]
        prefix = self.tr("map.level", z) + " " if z != old_z else ""
        self.say(prefix + extra + self.text())

    def on_key(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_TAB:
            flags = wx.NavigationKeyEvent.IsBackward if event.ShiftDown() else wx.NavigationKeyEvent.IsForward
            return self.canvas.Navigate(flags)
        if event.HasAnyModifiers():
            return event.Skip()
        if key in KEY_DIRS:
            d = KEY_DIRS[key]
            target = self.amap.step(self.sel, d)
            if target is None:
                if d in ("up", "down"):
                    return self.say(self.tr("map.nolevel", self.tr("dir." + d)))
                return self.say(self.tr("map.edge", self.tr("dir." + d)))
            return self.select(target)
        if key in (wx.WXK_HOME, wx.WXK_NUMPAD_HOME):
            if self.here is not None:
                return self.select(self.here)
            return
        if key == wx.WXK_SPACE:
            return self.say(self.text())
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            return self.walk()
        if key == wx.WXK_ESCAPE:
            return self.EndModal(wx.ID_CANCEL)
        event.Skip()

    def walk(self):
        self.choice = self.sel
        self.EndModal(wx.ID_OK)
