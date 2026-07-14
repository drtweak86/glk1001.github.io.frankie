"""Shared helpers for the built-in Spotify Connect (librespot) feature.

Ported from the standalone 'service.librespot' addon (v12.3.1.0, RPiOS/ALSA
one-shot edition). Keeps that addon's helper API so the other connect modules
stay close to the reference, but settings are re-keyed to 'connect_*' ids in
this addon's settings.xml and logging goes through the main addon's log_msg.
"""

import inspect
import os

import xbmcaddon
import xbmcgui

from utils import ADDON_DATA_PATH, ADDON_ID, get_formatted_caller_name, log_msg

# Same paths as the standalone service.librespot addon, so a box that already
# ran it gets a no-compile upgrade (see resources/install/install-root.sh).
LIBRESPOT_BINARY = "/usr/local/bin/librespot-frankie"

# Runtime files (FIFO, lock) live in this addon's profile directory.
ADDON_HOME = ADDON_DATA_PATH

_SETTINGS = {
    "connect_alsa_device": "default",
    "connect_backend": "kodi",
    "connect_dnd_kodi": "false",
    "connect_enabled": "true",
    # "{}" is filled with the system hostname (see librespot.py).
    "connect_name": "{}",
    "connect_player": "default",
    "connect_zeroconf_fixed": "false",
    "connect_zeroconf_port": "50252",
}

NOTIFICATION_HEADING = "Spotify Connect"

os.makedirs(ADDON_HOME, exist_ok=True)


def get_setting(key: str) -> str:
    # A fresh Addon object each call: old-style settings read as "" until the
    # user first touches them, and stale Addon instances can cache values.
    setting = xbmcaddon.Addon(id=ADDON_ID).getSetting(key)
    return setting if setting else _SETTINGS[key]


def setting_is_true(key: str) -> bool:
    return get_setting(key).lower() == "true"


def log(message: str) -> None:
    frame = inspect.stack()[1]
    caller_name = "connect." + get_formatted_caller_name(frame[1], frame[3])
    log_msg(message, caller_name=caller_name)


def logged_method(method):
    def logger(*args, **kwargs):
        log_msg("Called.", caller_name=f"{method.__module__}:{method.__qualname__}")
        return method(*args, **kwargs)

    return logger


def call_if_has(target, method_name, *args, **kwargs):
    method = getattr(target, method_name, None)
    if callable(method):
        return method(*args, **kwargs)
    return None


def notification(message="", heading=NOTIFICATION_HEADING, icon="", sound=False, time=5000):
    if not icon:
        icon = xbmcaddon.Addon(id=ADDON_ID).getAddonInfo("icon")
    xbmcgui.Dialog().notification(heading, message, icon, time, sound)


def set_inputstream_if_available(list_item) -> None:
    try:
        xbmcaddon.Addon("inputstream.ffmpeg")
        list_item.setProperty("inputstream", "inputstream.ffmpeg")
        log("Using inputstream.ffmpeg")
    except Exception:
        # Kodi can hand RTP directly to its internal FFmpeg player.
        log("inputstream.ffmpeg is not installed; using Kodi's native RTP handling")
