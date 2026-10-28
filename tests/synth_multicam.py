"""Three synthetic angles of one two-person conversation: a wide (room mix) and two singles whose lavalier favours its
speaker, each starting at a different offset into the session. Picture = flat colour with the angle name."""
import subprocess
import numpy as np


def make(folder, speech_path, truth, offsets=(0.0, 0.73, 1.41)):
    import wave
    with wave.open(str(speech_path)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64) / 32768
    a_mask = np.zeros(len(x))
    for r in truth["regions"]:
        if r["speaker"] == "A":
            a_mask[int(r["start"] * sr):int(r["end"] * sr)] = 1
    for f in truth["fillers"]:
        if f["speaker"] == "A":
            a_mask[int(f["start"] * sr):int(f["end"] * sr)] = 1
    mixes = {"wide": x, "camA": x * (.25 + .75 * a_mask), "camB": x * (1 - .75 * a_mask)}
    colors = {"wide": "0x404858", "camA": "0x7a3b2e", "camB": "0x2e5a7a"}
    paths = {}
    rng = np.random.default_rng(5)
    for (name, sig), off in zip(mixes.items(), offsets):
        pre = rng.normal(0, 1e-3, int(off * sr))  # the camera started earlier: extra lead-in before the session
        y = np.concatenate([pre, sig])
        wav = folder / f"{name}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(sr), "-ac", "1", "-i", "-", str(wav)], input=y.tobytes(), check=True)
        mp4 = folder / f"{name}.mp4"
        dur = len(y) / sr
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colors[name]}:s=320x180:r=30:d={dur:.3f}", "-i", str(wav),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", str(mp4)], check=True)
        paths[name] = mp4
    return paths
