import datetime
import os
import sys
import threading
import traceback

import wx

from dlclient import prefs
from dlclient.ui import MainFrame
from dlclient.version import VERSION


def log_path():
    return os.path.join(prefs.folder(), "error.log")


def write_error(kind, value, tb):
    try:
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write("\n%s, version %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), VERSION))
            f.write("".join(traceback.format_exception(kind, value, tb)))
    except OSError:
        pass


def install_error_log():
    if sys.stderr is None:
        try:
            sys.stderr = open(log_path(), "a", encoding="utf-8", buffering=1)
        except OSError:
            pass
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    sys.excepthook = write_error
    threading.excepthook = lambda a: write_error(a.exc_type, a.exc_value, a.exc_traceback)


def main():
    install_error_log()
    app_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    app = wx.App(False)
    frame = MainFrame(app_dir)
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
