"""Optional Pexels search/import. No key needed for local library operation."""
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse
import httpx
from . import store
from .media import register


def search(query):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise ValueError("Chưa đặt PEXELS_API_KEY. Có thể tải tư liệu riêng để dựng ngay.")
    with httpx.Client(timeout=30) as client:
        result = client.get("https://api.pexels.com/v1/search", params={"query":query,"per_page":12},headers={"Authorization":key})
        result.raise_for_status()
    return [{"id":p["id"],"thumbnail":p["src"]["medium"],"download":p["src"]["large2x"],
             "source_url":p["url"],"author":p["photographer"],"alt":p.get("alt","")} for p in result.json()["photos"]]


def import_photo(pid, photo_id, query):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise ValueError("Chưa cấu hình Pexels")
    with httpx.Client(timeout=60,follow_redirects=False) as client:
        result = client.get(f"https://api.pexels.com/v1/photos/{int(photo_id)}",headers={"Authorization":key})
        result.raise_for_status()
        photo = result.json()
        url = photo["src"]["large2x"]
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "images.pexels.com":
            raise ValueError("Nguồn tải Pexels không hợp lệ")
        target = store.folder(pid)/"assets"/(str(uuid.uuid4())+".jpg")
        target.parent.mkdir(parents=True,exist_ok=True)
        try:
            size = 0
            with client.stream("GET",url) as response, target.open("wb") as f:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 30*1024*1024:
                        raise ValueError("Ảnh tải vượt 30 MB")
                    f.write(chunk)
            return register(pid,target,photo.get("alt") or f"Pexels {photo_id}",tags=query+" "+photo.get("alt",""),source_url=photo["url"])
        except Exception:
            target.unlink(missing_ok=True)
            raise
