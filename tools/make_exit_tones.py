import os
import wave

import numpy as np

RATE = 44100
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sounds", "exits")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(7)


def pluck(freq, length=0.32, glide_to=None, pan=0.0, volume=0.6, bright=0.55):
    n = int(RATE * length)
    out = np.zeros(n)
    period = RATE / freq
    size = int(period) + 2
    buf = rng.uniform(-1, 1, size)
    buf = np.convolve(buf, [bright, 1 - bright], mode="same")
    pos = 0.0
    last = 0.0
    for i in range(n):
        if glide_to:
            f = freq * (glide_to / freq) ** min(1.0, i / (RATE * 0.08))
            period = RATE / f
        idx = int(pos) % size
        nxt = (idx + 1) % size
        sample = 0.5 * (buf[idx] + buf[nxt])
        sample = 0.996 * (0.6 * sample + 0.4 * last)
        last = sample
        buf[idx] = sample
        out[i] = sample
        pos += size / period
    t = np.arange(n) / RATE
    out *= np.exp(-t * 9) * volume
    click = rng.uniform(-1, 1, int(RATE * 0.003)) * 0.25 * np.linspace(1, 0, int(RATE * 0.003))
    out[:len(click)] += click
    left = out * np.sqrt((1 - pan) / 2)
    right = out * np.sqrt((1 + pan) / 2)
    return np.stack([left, right], axis=1)


def room_reverb(x, mix=0.15):
    y = x.copy()
    for delay, gain in ((0.019, 0.5), (0.029, 0.4), (0.043, 0.3)):
        d = int(RATE * delay)
        pad = np.zeros_like(x)
        pad[d:] = x[:-d] * gain
        y += pad * mix
    return np.concatenate([y, np.zeros((int(RATE * 0.15), 2))])


EXITS = {
    "north": lambda: pluck(988),
    "south": lambda: pluck(494),
    "east": lambda: pluck(784, pan=0.8),
    "west": lambda: pluck(784, pan=-0.8),
    "up": lambda: pluck(659, glide_to=988),
    "down": lambda: pluck(988, glide_to=659),
}


def save(name, data):
    data = room_reverb(data)
    data = data / (np.max(np.abs(data)) or 1) * 0.8
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((data * 32767).astype("<i2").tobytes())


for name, fn in EXITS.items():
    save(name, fn())

print("ok")
