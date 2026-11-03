"""MUD Sound Protocol player, after mudjs src/sound.js.

Sounds come only from the bundled library (sounds/manifest.json). A name is a
path without extension and may hold * and ? wildcards; several matches pick one
at random. A U= download URL from the server is ignored on purpose.

Effects share one channel with MSP priority: a new sound stops the playing one
only if its priority is strictly higher. Music has its own channel.
"""

import fnmatch
import json
import os
import random

try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
except ImportError:  # sound is optional
    pygame = None

TYPES = ["combat", "alert", "chat", "ui", "ambient", "music"]


def _int(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


class SoundPlayer:
    def __init__(self, folder, prefs):
        self.folder = folder
        self.prefs = prefs          # dict: mute, master, types{}
        self.library = []
        self.cache = {}
        self.effect = None          # (channel, priority)
        self.music_name = None
        self.ok = False
        try:
            with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
                self.library = json.load(f).get("sounds", [])
        except (OSError, ValueError):
            self.library = []
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
            self.cache[f] = pygame.mixer.Sound(os.path.join(self.folder, f))
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
        if not entry:
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
        if not entry:
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
        """Play a library sound by exact name, for the sound picker."""
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
