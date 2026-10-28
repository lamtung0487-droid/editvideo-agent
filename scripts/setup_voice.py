"""Download the offline Vietnamese Piper voice (vi_VN vais1000 medium, ~63 MB) into data/models/piper.
Run by `setup.ps1 -Voice` after `pip install -r requirements.voice.txt`. Sizes are checked. With --whisper it also
fetches Whisper `small` (~480 MB), which times offline words and runs the listen-back check."""
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/"
FILES = (("vi_VN-vais1000-medium.onnx", 63201294), ("vi_VN-vais1000-medium.onnx.json", 4860), ("MODEL_CARD", 361))


def main():
    root = ROOT / "data" / "models" / "piper"
    root.mkdir(parents=True, exist_ok=True)
    for name, size in FILES:
        dest = root / (name if name != "MODEL_CARD" else "vi_VN-vais1000-medium.MODEL_CARD.txt")
        if dest.exists() and dest.stat().st_size == size:
            print("present", dest.name)
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(urllib.request.Request(BASE + name, headers={"User-Agent": "EditVideoAgent"}), timeout=120) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        if tmp.stat().st_size != size:
            tmp.unlink()
            sys.exit(f"{name}: unexpected size")
        tmp.replace(dest)
        print("downloaded", dest.name, size)
    print("Voice model card (licence of the training data):")
    print((root / "vi_VN-vais1000-medium.MODEL_CARD.txt").read_text(encoding="utf-8"))


def whisper():
    """Whisper `small` (CTranslate2, MIT, ~480 MB) into data/models: it times the words of offline narration and runs
    the listen-back check. Fetched only with --whisper."""
    sys.path.insert(0, str(ROOT))
    from faster_whisper import WhisperModel
    WhisperModel("small", device="cpu", compute_type="int8", download_root=str(ROOT / "data" / "models"))
    print("Whisper small ready in data/models")


if __name__ == "__main__":
    main()
    if "--whisper" in sys.argv:
        whisper()
