import fnmatch
import json
import os
import random
import re
import urllib.request

LIVE_BASE = "https://dreamland.rocks/play/sounds/"
SAFE_FILE = re.compile(r"^[a-z0-9_-]+/[a-z0-9_.-]+\.(mp3|ogg|wav)$", re.I)

try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
except ImportError:
    pygame = None

TYPES = ["combat", "alert", "chat", "ui", "ambient", "music"]


def _int(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


class SoundPlayer:
    def __init__(self, folder, prefs, live_folder=None):
        self.folder = folder
        self.live_folder = live_folder
        self.prefs = prefs
        self.library = []
        self.cache = {}
        self.effect = None
        self.music_name = None
        self.ok = False
        self.on_missing = None
        self.reload()
        if pygame:
            try:
                pygame.mixer.init()
                pygame.mixer.set_num_channels(8)
                self.effect_channel = pygame.mixer.Channel(0)
                self.music_channel = pygame.mixer.Channel(1)
                self.preview_channel = pygame.mixer.Channel(2)
                self.ok = True
            except Exception:
                self.ok = False

    def reload(self):
        for folder in (self.live_folder, self.folder):
            if not folder:
                continue
            try:
                with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
                    sounds = json.load(f).get("sounds", [])
            except (OSError, ValueError):
                continue
            self.library = [x for x in sounds if isinstance(x, dict) and SAFE_FILE.match(str(x.get("file", "")))
                            and isinstance(x.get("name"), str)]
            self.cache = {}
            return

    def path_for(self, file):
        for folder in (self.live_folder, self.folder):
            if folder and os.path.exists(os.path.join(folder, file)):
                return os.path.join(folder, file)
        return None

    def resolve(self, name):
        if not name:
            return None
        clean = name.replace("\\", "/").lstrip("/")
        for ext in (".wav", ".mid", ".ogg", ".mp3"):
            if clean.lower().endswith(ext):
                clean = clean[: -len(ext)]
        if ".." in clean.split("/"):
            return None
        hits = [s for s in self.library if fnmatch.fnmatchcase(s["name"].lower(), clean.lower())]
        if not hits and "/" not in clean:
            hits = [s for s in self.library
                    if fnmatch.fnmatchcase(s["name"].split("/")[-1].lower(), clean.lower())]
        return random.choice(hits) if hits else None

    def _sound(self, entry):
        f = entry["file"]
        if f not in self.cache:
            path = self.path_for(f)
            if not path:
                raise OSError(f)
            self.cache[f] = pygame.mixer.Sound(path)
        return self.cache[f]

    def gain(self, kind, v):
        p = self.prefs
        if p.get("mute"):
            return 0.0
        t = p.get("types", {}).get(kind, 100)
        return (p.get("master", 80) / 100) * (t / 100) * (v / 100)

    def handle(self, kind, name, opts):
        if kind == "music":
            self.play_music(name, opts)
        else:
            self.play(name, opts)

    def play(self, name, opts=None):
        opts = opts or {}
        if not self.ok:
            return
        if name.lower() == "off":
            return self.effect_channel.stop()
        if self.prefs.get("mute"):
            return
        entry = self.resolve(name)
        if not entry or not self.path_for(entry["file"]):
            if self.on_missing:
                self.on_missing("sound", name, opts)
            return
        v = _int(opts.get("V"), 0, 100, 100)
        loops = _int(opts.get("L"), -1, 100, 1) or 1
        p = _int(opts.get("P"), 0, 100, 50)
        kind = (opts.get("T") or entry.get("type") or "alert").lower()
        if self.effect_channel.get_busy() and self.effect and p <= self.effect:
            return
        try:
            snd = self._sound(entry)
        except Exception:
            return
        self.effect_channel.set_volume(self.gain(kind, v))
        self.effect_channel.play(snd, loops=-1 if loops < 0 else loops - 1)
        self.effect = p

    def play_music(self, name, opts=None):
        opts = opts or {}
        if not self.ok:
            return
        if name.lower() == "off":
            self.music_name = None
            return self.music_channel.stop()
        if self.prefs.get("mute"):
            return
        entry = self.resolve(name)
        if not entry or not self.path_for(entry["file"]):
            if self.on_missing:
                self.on_missing("music", name, opts)
            return
        v = _int(opts.get("V"), 0, 100, 100)
        loops = _int(opts.get("L"), -1, 100, 1) or 1
        cont = _int(opts.get("C"), 0, 1, 1) == 1
        self.music_channel.set_volume(self.gain("music", v))
        if cont and self.music_name == name and self.music_channel.get_busy():
            return
        try:
            snd = self._sound(entry)
        except Exception:
            return
        self.music_channel.play(snd, loops=-1 if loops < 0 else loops - 1)
        self.music_name = name

    def preview(self, name):
        if not self.ok:
            return
        entry = next((s for s in self.library if s["name"] == name), None)
        if entry:
            self.preview_channel.set_volume(self.gain(entry.get("type", "ui"), 100) or 0.0)
            self.preview_channel.play(self._sound(entry))

    def stop_all(self):
        if self.ok:
            pygame.mixer.stop()
        self.effect = None
        self.music_name = None


def fetch_live_library(live_folder, bundled_folder, timeout=15):
    req = urllib.request.Request(LIVE_BASE + "manifest.json", headers={"User-Agent": "DreamLand desktop client"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(2_000_000)
    data = json.loads(raw.decode("utf-8"))
    sounds = data.get("sounds")
    if not isinstance(sounds, list):
        return False
    os.makedirs(live_folder, exist_ok=True)
    for x in sounds:
        f = str((x or {}).get("file", ""))
        if not SAFE_FILE.match(f):
            continue
        target = os.path.join(live_folder, *f.split("/"))
        if os.path.exists(target) or os.path.exists(os.path.join(bundled_folder, *f.split("/"))):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        req = urllib.request.Request(LIVE_BASE + f, headers={"User-Agent": "DreamLand desktop client"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(5_000_000)
        with open(target + ".part", "wb") as out:
            out.write(body)
        os.replace(target + ".part", target)
    tmp = os.path.join(live_folder, "manifest.json.part")
    with open(tmp, "wb") as out:
        out.write(raw)
    os.replace(tmp, os.path.join(live_folder, "manifest.json"))
    return True


def fetch_from_url(url, live_folder, timeout=15):
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in ("dreamland.rocks", "www.dreamland.rocks"):
        return None
    base = u.path.rsplit("/", 1)[-1]
    if not re.match(r"^[a-z0-9_.-]+\.(mp3|ogg|wav)$", base, re.I):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "DreamLand desktop client"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(5_000_000)
    target = os.path.join(live_folder, "server", base)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target + ".part", "wb") as out:
        out.write(body)
    os.replace(target + ".part", target)
    name = "server/" + base.rsplit(".", 1)[0]
    path = os.path.join(live_folder, "manifest.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {"sounds": []}
    sounds = [x for x in data.get("sounds", []) if x.get("name") != name]
    sounds.append({"name": name, "type": "alert", "file": "server/" + base, "source": url})
    data["sounds"] = sounds
    with open(path + ".part", "w", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, indent=1)
    os.replace(path + ".part", path)
    return name
