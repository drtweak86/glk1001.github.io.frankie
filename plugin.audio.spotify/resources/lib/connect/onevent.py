# librespot --onevent hook. librespot runs this under the SYSTEM python3
# (/usr/bin/python3), not Kodi's interpreter, once per player event, with the
# event details in environment variables. It forwards them as JSON over a
# loopback UDP datagram to the EventHandler port given as argv[1].
# It must therefore stay pure-stdlib and runnable as a standalone script —
# no Kodi imports, no imports from this addon.
# Ported byte-identical from service.librespot 12.3.1.0.

import json
import os
import socket
import sys
import time

HOST = "127.0.0.1"
SOCK_AF = socket.AF_INET
SOCK_TYPE = socket.SOCK_DGRAM


def _get(key):
    return os.environ.get(key, "")


def _get_first(key):
    return os.environ.get(key, "").partition("\n")[0]


def _get_time(key):
    try:
        return int(os.environ.get(key, "0")) / 1000
    except (TypeError, ValueError):
        return 0


def _on_event():
    event = _get("PLAYER_EVENT")
    payload = {}
    if event in ("paused", "playing", "position_correction", "seeked"):
        payload["position"] = _get_time("POSITION_MS")
        payload["then"] = time.time()
    elif event == "track_changed":
        payload["art"] = _get_first("COVERS")
        payload["duration"] = round(_get_time("DURATION_MS"))
        payload["title"] = _get("NAME")
        item_type = _get("ITEM_TYPE")
        if item_type == "Track":
            payload["album"] = _get("ALBUM")
            payload["artist"] = _get_first("ARTISTS")
        elif item_type == "Episode":
            payload["album"] = _get("SHOW_NAME")
    elif event == "stopped":
        pass
    else:
        return
    send_event(int(sys.argv[1]), event, payload)


def send_event(port, event="", payload=None):
    if payload is None:
        payload = {}
    data = json.dumps([event, payload]).encode("utf-8")
    with socket.socket(SOCK_AF, SOCK_TYPE) as sock:
        sock.sendto(data, (HOST, port))


if __name__ == "__main__":
    _on_event()
