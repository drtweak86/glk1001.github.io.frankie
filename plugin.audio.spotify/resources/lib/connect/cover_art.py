"""Cover-art to 16:9 fanart conversion with a small on-disk cache.

Ported from service.librespot 12.3.1.0 (there: resources/lib/spotify.py).
Falls back to returning the raw cover URL when PIL is unavailable.
"""

import os
import tempfile
import urllib.request

try:
    import PIL.Image
except ImportError:
    PIL = None

_DIRECTORY_PATH = os.path.join(tempfile.gettempdir(), "librespot.coverart")
_MAX_COVERARTS = 10


def get_fanart(url):
    if not url:
        return ""
    if PIL is None:
        return url

    name = os.path.basename(url.split("?", 1)[0]) or "cover"
    target = os.path.join(_DIRECTORY_PATH, name + ".jpg")
    if os.path.exists(target):
        return target

    os.makedirs(_DIRECTORY_PATH, exist_ok=True)
    paths = [
        os.path.join(_DIRECTORY_PATH, filename)
        for filename in os.listdir(_DIRECTORY_PATH)
    ]
    paths = [path for path in paths if os.path.isfile(path)]
    paths.sort(key=os.path.getmtime)
    for path in paths[:-_MAX_COVERARTS]:
        try:
            os.remove(path)
        except OSError:
            pass

    source = target + ".tmp"
    try:
        urllib.request.urlretrieve(url, source)
        image = PIL.Image.open(source).convert("RGB")
        width, height = image.size
        new_width = max(width, int(height * 16 / 9))
        delta_w = new_width - width
        new_image = PIL.Image.new("RGB", (new_width, height), (0, 0, 0))
        new_image.paste(image, (delta_w // 2, 0))
        new_image.save(target, "JPEG", optimize=True)
        return target
    except Exception:
        return url
    finally:
        try:
            os.remove(source)
        except OSError:
            pass
