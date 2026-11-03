import os
import sys

import wx

from dlclient.ui import MainFrame


def main():
    app_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    app = wx.App(False)
    frame = MainFrame(app_dir)
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
