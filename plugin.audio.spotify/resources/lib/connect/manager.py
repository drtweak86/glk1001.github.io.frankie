"""Reconciles the desired Spotify Connect state onto a background thread.

Owns the generator-based session lifecycle ported from service.librespot's
monitor.py, but drives it from a single worker thread instead of Kodi's
onSettingsChanged callback directly, and adds:
  - a snapshot-compare so unrelated addon settings changes (e.g. toggling
    the main plugin's normalization setting) don't restart librespot;
  - a platform gate (Linux only, not Android);
  - a first-activation confirm dialog before the sudo installer runs;
  - a pause while the plugin's own spotty zeroconf auth flow is active;
  - a guard against running alongside the standalone service.librespot addon;
  - a single-instance flock, since this can outlive addon restarts briefly.
"""

import fcntl
import os
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui

from utils import ADDON_DATA_PATH, log_msg
from . import bootstrap, session, session_kodi
from . import utils as connect_utils

_LOCK_FILE = os.path.join(ADDON_DATA_PATH, "connect.lock")
_AUTH_PAUSE_PROPERTY = "spotify-connect-auth-active"
_AUTH_PAUSE_WINDOW_ID = 10000
_AUTH_PAUSE_STALE_SECS = 300
_TICK_SECS = 2
_STANDALONE_ADDON_ID = "service.librespot"

_SETTINGS_KEYS = (
    "connect_enabled",
    "connect_name",
    "connect_backend",
    "connect_player",
    "connect_alsa_device",
    "connect_dnd_kodi",
    "connect_zeroconf_fixed",
    "connect_zeroconf_port",
)


def _snapshot():
    return tuple(connect_utils.get_setting(key) for key in _SETTINGS_KEYS)


def _platform_ok():
    return xbmc.getCondVisibility(
        "System.Platform.Linux + !System.Platform.Android"
    )


def _standalone_addon_present():
    try:
        xbmcaddon.Addon(_STANDALONE_ADDON_ID)
        return True
    except RuntimeError:
        return False


def _auth_paused():
    value = xbmcgui.Window(_AUTH_PAUSE_WINDOW_ID).getProperty(_AUTH_PAUSE_PROPERTY)
    if not value:
        return False
    try:
        started = int(value)
    except ValueError:
        return False
    if time.time() - started > _AUTH_PAUSE_STALE_SECS:
        # The plugin process died mid-auth without clearing the property.
        log_msg("connect: auth-pause property is stale; clearing it.")
        xbmcgui.Window(_AUTH_PAUSE_WINDOW_ID).clearProperty(_AUTH_PAUSE_PROPERTY)
        return False
    return True


def _build_generator():
    zeroconf_port = "0"
    if connect_utils.setting_is_true("connect_zeroconf_fixed"):
        zeroconf_port = connect_utils.get_setting("connect_zeroconf_port")

    if connect_utils.get_setting("connect_backend") == "alsa":
        service_ = session.Service(
            "alsa", connect_utils.get_setting("connect_alsa_device"), zeroconf_port
        )
    else:
        service_ = session_kodi.Service(zeroconf_port)
    return service_.run()


class ConnectManager:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._settings_changed = threading.Event()
        self._lock_handle = None
        self._standalone_warned = False

    def start(self):
        if not _platform_ok():
            log_msg("connect: not starting Spotify Connect (Linux-only feature).")
            return

        self._lock_handle = self._acquire_lock()
        if self._lock_handle is None:
            log_msg("connect: another Spotify Connect instance already holds the lock.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="spotify-connect-manager", daemon=True
        )
        self._thread.start()

    def stop(self):
        if self._thread is None:
            return
        self._stop_event.set()
        self._settings_changed.set()
        self._thread.join(timeout=10)
        self._thread = None
        self._release_lock()

    def on_settings_changed(self):
        self._settings_changed.set()

    @staticmethod
    def _acquire_lock():
        os.makedirs(ADDON_DATA_PATH, exist_ok=True)
        handle = open(_LOCK_FILE, "w", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        return handle

    def _release_lock(self):
        if self._lock_handle is None:
            return
        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            self._lock_handle.close()
        except Exception:
            pass
        self._lock_handle = None

    def _desired_enabled(self):
        if not connect_utils.setting_is_true("connect_enabled"):
            return False
        if _standalone_addon_present():
            if not self._standalone_warned:
                log_msg(
                    "connect: the standalone service.librespot addon is installed; "
                    "not starting the built-in Spotify Connect feature to avoid "
                    "clashing over the librespot binary and RTP port. Disable or "
                    "uninstall service.librespot to use this instead.",
                )
                connect_utils.notification(
                    "Disable the old service.librespot addon to use the "
                    "built-in Spotify Connect",
                    time=10000,
                )
                self._standalone_warned = True
            return False
        return True

    def _run(self):
        generator = None
        running_snapshot = None
        try:
            while not self._stop_event.is_set():
                self._settings_changed.wait(_TICK_SECS)
                self._settings_changed.clear()

                desired = self._desired_enabled() and not _auth_paused()

                if desired and generator is None:
                    if not bootstrap.ready():
                        if not bootstrap.confirm_and_install():
                            continue
                    generator = _build_generator()
                    next(generator)
                    running_snapshot = _snapshot()
                elif not desired and generator is not None:
                    self._close_generator(generator)
                    generator = None
                    running_snapshot = None
                elif desired and generator is not None:
                    current = _snapshot()
                    if current != running_snapshot:
                        log_msg("connect: settings changed; rebuilding Spotify Connect session.")
                        try:
                            next(generator)
                        except StopIteration:
                            generator = _build_generator()
                            next(generator)
                        running_snapshot = current
        finally:
            if generator is not None:
                self._close_generator(generator)

    @staticmethod
    def _close_generator(generator):
        try:
            generator.close()
        except Exception as exc:
            log_msg(f"connect: error closing Spotify Connect session: {exc!r}")
