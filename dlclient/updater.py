import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from .version import REPO, VERSION

API = "https://api.github.com/repos/%s/releases/latest" % REPO
EXE = "DreamLand.exe"
ALLOWED_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")


def parse_version(text):
    parts = []
    for piece in str(text).lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (3 - len(parts)))


def is_newer(tag, current=VERSION):
    return parse_version(tag) > parse_version(current)


def frozen():
    return bool(getattr(sys, "frozen", False))


def app_folder():
    return os.path.dirname(sys.executable) if frozen() else None


def latest(timeout=15):
    req = urllib.request.Request(API, headers={"User-Agent": "DreamLand desktop client",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read(2_000_000).decode("utf-8"))
    asset = next((a for a in data.get("assets", []) if str(a.get("name", "")).lower().endswith(".zip")), None)
    return {
        "tag": data.get("tag_name", ""),
        "notes": data.get("body") or "",
        "url": asset.get("browser_download_url") if asset else None,
        "page": data.get("html_url", ""),
    }


def _host_ok(url):
    from urllib.parse import urlparse
    u = urlparse(url)
    return u.scheme == "https" and u.hostname in ALLOWED_HOSTS


def download(url, progress=None, timeout=60):
    if not _host_ok(url):
        raise ValueError("unexpected download host")
    work = tempfile.mkdtemp(prefix="dlclient-update-")
    target = os.path.join(work, "update.zip")
    req = urllib.request.Request(url, headers={"User-Agent": "DreamLand desktop client"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(target, "wb") as out:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            block = r.read(256 * 1024)
            if not block:
                break
            out.write(block)
            got += len(block)
            if progress and total:
                progress(got * 100 // total)
    unpacked = os.path.join(work, "files")
    with zipfile.ZipFile(target) as z:
        for name in z.namelist():
            dest = os.path.realpath(os.path.join(unpacked, name))
            if not dest.startswith(os.path.realpath(unpacked) + os.sep) and dest != os.path.realpath(unpacked):
                raise ValueError("bad path in update")
        z.extractall(unpacked)
    root = unpacked
    entries = os.listdir(unpacked)
    if EXE not in entries and len(entries) == 1 and os.path.isdir(os.path.join(unpacked, entries[0])):
        root = os.path.join(unpacked, entries[0])
    if not os.path.isfile(os.path.join(root, EXE)):
        shutil.rmtree(work, ignore_errors=True)
        raise ValueError("the update has no " + EXE)
    return work, root


def apply_and_restart(work, root):
    dest = app_folder()
    if not dest:
        raise RuntimeError("not a packaged copy")
    script = os.path.join(work, "update.cmd")
    with open(script, "w", encoding="utf-8") as f:
        f.write("@echo off\r\n")
        f.write("chcp 65001 >nul\r\n")
        f.write(":wait\r\n")
        f.write('tasklist /FI "PID eq %d" 2>nul | find "%d" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
                % (os.getpid(), os.getpid()))
        f.write('robocopy "%s" "%s" /E /R:5 /W:1 /NFL /NDL /NJH /NJS /NP >nul\r\n' % (root, dest))
        f.write('start "" "%s"\r\n' % os.path.join(dest, EXE))
        f.write('rmdir /s /q "%s"\r\n' % work)
    subprocess.Popen(["cmd.exe", "/c", script], creationflags=0x08000000 | 0x00000200,
                     close_fds=True, cwd=tempfile.gettempdir())
