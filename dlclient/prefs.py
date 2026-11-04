import json
import os

DEFAULTS = {
    "lang": "en",
    "speech": True,
    "echo": True,
    "hide_prompt": True,
    "autologin": {"enabled": False, "name": ""},
    "default_keys": True,
    "sound": {
        "mute": False,
        "master": 80,
        "types": {"combat": 100, "alert": 100, "chat": 100, "ui": 100, "ambient": 60, "music": 50},
    },
    "theme": "dark",
    "game_colors": True,
    "font": {"face": "Consolas", "size": 12},
    "speech_skip": [],
    "log_session": False,
    "check_updates": True,
    "exit_tones": True,
    "list_menus": True,
    "room_sounds": {"player": True, "mob": True, "item": True, "target": True},
    "server": "",
    "history": [],
    "vars": {},
}


def folder():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "DreamLandClient")
    os.makedirs(path, exist_ok=True)
    return path


def _merge(defaults, saved):
    out = dict(defaults)
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(defaults.get(k), dict):
            out[k] = _merge(defaults[k], v)
        else:
            out[k] = v
    return out


def load():
    try:
        with open(os.path.join(folder(), "settings.json"), encoding="utf-8") as f:
            return _merge(DEFAULTS, json.load(f))
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULTS))


def save(prefs):
    path = os.path.join(folder(), "settings.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
