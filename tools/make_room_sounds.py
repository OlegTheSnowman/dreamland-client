import os
import wave

import numpy as np

RATE = 44100
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sounds", "room")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(3)


def t_of(length):
    return np.arange(int(RATE * length)) / RATE


def stereo(x):
    return np.stack([x, x], axis=1) * np.sqrt(0.5)


def wood(freq, length=0.18, vol=0.7):
    t = t_of(length)
    body = np.sin(2 * np.pi * freq * t) * np.exp(-t * 35) + 0.5 * np.sin(2 * np.pi * freq * 2.7 * t) * np.exp(-t * 60)
    click = rng.uniform(-1, 1, len(t)) * np.exp(-t * 400) * 0.4
    return stereo((body + click) * vol)


def bubble(f0, f1, length, vol):
    t = t_of(length)
    f = f0 * (f1 / f0) ** (t / length)
    env = np.sin(np.pi * np.minimum(1, t / length)) ** 1.5
    return stereo(np.sin(2 * np.pi * np.cumsum(f) / RATE) * env * vol)


def glass(freq, length=0.09, vol=0.3):
    t = t_of(length)
    x = np.sin(2 * np.pi * freq * t) * np.exp(-t * 60) + 0.4 * np.sin(2 * np.pi * freq * 2.3 * t) * np.exp(-t * 90)
    return stereo(x * np.minimum(1, t / 0.001) * vol)


def metal(freq, length=0.15, vol=0.35, decay=30):
    t = t_of(length)
    x = np.zeros_like(t)
    for ratio, amp in ((1.0, 1.0), (2.76, 0.45), (5.40, 0.2), (8.93, 0.08)):
        x += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t * decay * (1 + ratio * 0.3))
    return stereo(x * np.minimum(1, t / 0.0015) * vol)


def seq(parts):
    total = int(RATE * (max(at + len(s) / RATE for at, s in parts) + 0.1))
    buf = np.zeros((total, 2))
    for at, s in parts:
        i = int(RATE * at)
        buf[i:i + len(s)] += s
    return buf


SOUNDS = {
    "player": lambda: seq([(0, wood(700)), (0.1, wood(900))]),
    "mob": lambda: seq([(0, bubble(380, 220, 0.18, 0.7))]),
    "item": lambda: seq([(0, glass(1900))]),
    "target": lambda: seq([(i * 0.055, metal(1650)) for i in range(3)]),
}

for name, fn in SOUNDS.items():
    data = fn()
    data = data / (np.max(np.abs(data)) or 1) * 0.8
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((data * 32767).astype("<i2").tobytes())
print("ok")
