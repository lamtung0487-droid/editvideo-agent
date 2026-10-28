"""Synthetic test song with known structure: intro 8 bars, build 8, (0.5 s gap) peak 8, breakdown 4, peak 8, outro 4 at 120 BPM."""
import subprocess, sys
import numpy as np
SR = 44100
BPM = 120
BEAT = 60 / BPM
BAR = 4 * BEAT


def make(path, seed=3):
    rng = np.random.default_rng(seed)
    plan = [("intro", 8), ("build", 8), ("peak", 8), ("breakdown", 4), ("peak", 8), ("outro", 4)]
    total = sum(n for _, n in plan) * BAR + 1.0
    n = int(total * SR)
    x = np.zeros(n)
    t0 = 0.5
    truth = {"beats": [], "sections": [], "hit": None}
    def add(at, sig):
        i = int(at * SR)
        j = min(n, i + len(sig))
        x[i:j] += sig[: j - i]
    def kick(g):
        a = np.arange(int(.25 * SR)) / SR
        return g * np.sin(2 * np.pi * (50 + 90 * np.exp(-a * 35)) * a) * np.exp(-a * 14)
    def snare(g):
        a = np.arange(int(.18 * SR)) / SR
        return g * rng.normal(0, 1, len(a)) * np.exp(-a * 25)
    def hat(g):
        a = np.arange(int(.05 * SR)) / SR
        return g * np.diff(rng.normal(0, 1, len(a) + 1)) * np.exp(-a * 90)
    def pad(dur, f, g, bright=False):
        a = np.arange(int(dur * SR)) / SR
        s = sum(np.sin(2 * np.pi * f * k * a) / k ** (1.2 if bright else 2.5) for k in range(1, 9))
        return g * s * np.minimum(1, np.minimum(a / .05, (dur - a) / .05))
    t = t0
    for name, nb in plan:
        if name == "peak" and truth["hit"] is None:
            truth["gap"] = (t - .5, t)
            truth["hit"] = t
        truth["sections"].append((name, t))
        for b in range(nb):
            for q in range(4):
                bt = t + b * BAR + q * BEAT
                truth["beats"].append(bt)
                prog = (b * 4 + q) / (nb * 4)
                if name == "intro":
                    add(bt, hat(.05)); add(bt, kick(.12) if q == 0 else hat(.03))
                elif name == "build":
                    g = .15 + .45 * prog
                    add(bt, kick(g)); add(bt + BEAT / 2, hat(.08 + .1 * prog))
                    if q in (1, 3): add(bt, snare(g * .5))
                elif name == "peak":
                    add(bt, kick(.9)); add(bt + BEAT / 2, hat(.25))
                    if q in (1, 3): add(bt, snare(.6))
                elif name == "breakdown":
                    if q == 0: add(bt, kick(.15))
                elif name == "outro":
                    g = .5 * (1 - prog)
                    add(bt, kick(g))
            chord = [110, 87.3, 98, 130.8][b % 4]
            if name == "intro": add(t + b * BAR, pad(BAR, chord * 2, .04))
            elif name == "build": add(t + b * BAR, pad(BAR, chord * 2, .05 + .08 * b / nb, bright=b > nb / 2))
            elif name == "peak": add(t + b * BAR, pad(BAR, chord, .18, bright=True))
            elif name == "breakdown": add(t + b * BAR, pad(BAR, chord * 4, .08))
            elif name == "outro": add(t + b * BAR, pad(BAR, chord * 2, .08 * (1 - b / nb)))
        if name == "build":
            # silence the last half second before the drop (dip before the hit), then an impact
            i0, i1 = int((t + nb * BAR - .5) * SR), int((t + nb * BAR) * SR)
            x[i0:i1] *= .003
            truth["beats"] = [b_ for b_ in truth["beats"] if not (t + nb * BAR - .5 <= b_ < t + nb * BAR)]
            a = np.arange(int(1.2 * SR)) / SR
            add(t + nb * BAR, .9 * (np.sin(2 * np.pi * 45 * a) + .5 * rng.normal(0, 1, len(a))) * np.exp(-a * 4))
        t += nb * BAR
    x = x / np.abs(x).max() * .9
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_s16le", path], input=x.tobytes(), check=True)
    return truth


if __name__ == "__main__":
    import json
    print(json.dumps(make(sys.argv[1]), default=float)[:300])
