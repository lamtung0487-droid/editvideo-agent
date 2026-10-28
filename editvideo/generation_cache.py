"""Small, content-addressed prompt cache. No pickle, no downloaded weights.

BF16 outputs are stored losslessly as float32 NumPy arrays. Cache entries are
bounded and verified on read; a bad entry becomes a miss, never a model input.
"""
import hashlib
import json
import os
import uuid
import zipfile
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import numpy as np
from . import store
from .media import sha256

VERSION = "t5-bf16-256-v1"
MAX_BYTES = 128 * 1024 * 1024


def runtime_versions():
    versions={}
    for name in ('torch','transformers','diffusers','accelerate'):
        try:versions[name]=version(name)
        except PackageNotFoundError:versions[name]='unavailable'
    return versions


def prompt_key(prompt, artifacts, precision):
    names = ("text_encoder/", "tokenizer/", "t5xxl_")
    fingerprints = sorted((Path(r["path"]).name, r["sha256"]) for r in artifacts
                          if any(part in str(r["path"]).replace("\\", "/") for part in names))
    if not fingerprints:
        raise ValueError("Verified encoder/tokenizer artifacts required for prompt cache")
    identity = {"version": VERSION, "precision": precision, "runtime":runtime_versions(),"artifacts": fingerprints,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def cache_root():
    return store.DATA / "generation-cache" / "prompts"


def _paths(key):
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("Invalid cache key")
    return cache_root() / (key + ".npz"), cache_root() / (key + ".json")


def _validate(embeds, attention):
    if embeds.dtype != np.float32 or embeds.shape != (1, 256, 4096) or not np.isfinite(embeds).all():
        raise ValueError("Invalid cached prompt embedding")
    if attention.dtype != np.uint8 or attention.shape != (1, 256) or not np.isin(attention, [0, 1]).all():
        raise ValueError("Invalid cached attention mask")


def load(key):
    data, manifest = _paths(key)
    try:
        r = store.read_json(manifest)
        if r["version"] != VERSION or r["key"] != key or not 0 < data.stat().st_size < 8_000_000:
            return None
        if sha256(data) != r["sha256"]:
            return None
        with np.load(data, allow_pickle=False) as arrays:
            embeds, attention = arrays["embeds"], arrays["attention"]
        _validate(embeds, attention)
        if not isinstance(r["prompt_tokens"], int) or r["prompt_tokens"] < 1:
            return None
        os.utime(data, None)
        return embeds, attention, r
    except (OSError, ValueError, KeyError, TypeError, EOFError, zipfile.BadZipFile):
        return None


def save(key, embeds, attention, prompt_tokens, precision):
    _validate(embeds, attention)
    data, manifest = _paths(key)
    data.parent.mkdir(parents=True, exist_ok=True)
    tmp = data.with_name(key + "-" + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("wb") as f:
            np.savez(f, embeds=embeds, attention=attention)
        record = {"version": VERSION, "key": key, "sha256": sha256(tmp),
                  "prompt_tokens": prompt_tokens, "precision": precision, "bytes": tmp.stat().st_size}
        os.replace(tmp, data)
        store.write_json(manifest, record)
        # Generation holds the shared GPU lock, so normal writers are serialized.
        entries = sorted(data.parent.glob("*.npz"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        total = 0
        for p in entries:
            total += p.stat().st_size
            if total > MAX_BYTES and p != data:
                p.unlink(missing_ok=True)
                p.with_suffix(".json").unlink(missing_ok=True)
        return record
    finally:
        tmp.unlink(missing_ok=True)


def prepare_reference(path, width, height, fit="cover", crop=None):
    """Explicit geometric preprocessing shared by every reference frame."""
    from PIL import Image, ImageOps
    with Image.open(path) as original:
        im = ImageOps.exif_transpose(original).convert("RGBA")
        source_size = list(im.size)
        rgb = Image.new("RGBA", im.size, "#101820")
        rgb.alpha_composite(im)
        im = rgb.convert("RGB")
    bounds = [0, 0, im.width, im.height]
    if crop is not None:
        bounds = [round(crop[0]*im.width), round(crop[1]*im.height),
                  round(crop[2]*im.width), round(crop[3]*im.height)]
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise ValueError("Reference crop contains no pixels")
        im = im.crop(bounds)
    if fit == "cover":
        scale = max(width/im.width, height/im.height)
        cw, ch = width/scale, height/scale
        inner = [(im.width-cw)/2, (im.height-ch)/2, (im.width+cw)/2, (im.height+ch)/2]
        effective_crop = [bounds[0]+inner[0], bounds[1]+inner[1], bounds[0]+inner[2], bounds[1]+inner[3]]
        im = ImageOps.fit(im, (width, height), method=Image.Resampling.LANCZOS)
    elif fit == "contain":
        effective_crop = bounds
        im = ImageOps.pad(im, (width, height), method=Image.Resampling.LANCZOS, color="#101820")
    elif fit == "stretch":
        effective_crop = bounds
        im = im.resize((width, height), Image.Resampling.LANCZOS)
    else:
        raise ValueError("Reference fit cover|contain|stretch")
    return im, {"source_size": source_size, "source_crop_pixels": effective_crop,
                "output_size": [width, height], "fit": fit, "exif_transposed": True,
                "alpha_matte": "#101820"}
