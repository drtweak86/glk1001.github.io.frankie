"""First-run gate and one-shot installer for the Spotify Connect feature.

Ported from service.librespot 12.3.1.0. Before anything runs with sudo the
user is asked for confirmation; declining (or a failed install) switches the
connect_enabled setting off so Kodi restarts don't loop through the prompt.
"""

import os
import subprocess

import xbmcaddon
import xbmcgui
import xbmcvfs

from utils import ADDON_ID, log_msg
from . import utils as connect_utils

ADDON_PATH = xbmcvfs.translatePath(xbmcaddon.Addon(id=ADDON_ID).getAddonInfo("path"))
INSTALLER = os.path.join(ADDON_PATH, "resources", "install", "install-root.sh")
FFMPEG = "/usr/bin/ffmpeg"
# The --onevent hook runs under the system interpreter, not Kodi's.
SYSTEM_PYTHON = "/usr/bin/python3"
# Shared with the standalone service.librespot addon (see install-root.sh).
MARKER = "/var/lib/frankie-librespot/installed-0.8.0-alsa-r2"

DIALOG_HEADING = "Spotify Connect"

CONFIRM_INSTALL_MSG = (
    "Set up Spotify Connect?\n"
    "First-time setup uses sudo to install ffmpeg and the librespot binary "
    "(quick download; falls back to compiling on this machine, which can take "
    "20-40 minutes on a Pi). Choosing No disables Spotify Connect in the "
    "addon settings."
)


def ready() -> bool:
    return (
        os.path.isfile(connect_utils.LIBRESPOT_BINARY)
        and os.access(connect_utils.LIBRESPOT_BINARY, os.X_OK)
        and os.path.isfile(FFMPEG)
        and os.path.isfile(MARKER)
        and os.path.isfile(SYSTEM_PYTHON)
    )


def disable_connect_setting() -> None:
    try:
        xbmcaddon.Addon(id=ADDON_ID).setSetting("connect_enabled", "false")
    except Exception:
        pass


def confirm_and_install() -> bool:
    """Asks for consent, then runs the sudo installer. Returns readiness."""
    if not xbmcgui.Dialog().yesno(DIALOG_HEADING, CONFIRM_INSTALL_MSG):
        log_msg("User declined the Spotify Connect installation; disabling the setting.")
        disable_connect_setting()
        connect_utils.notification("Spotify Connect disabled (can be re-enabled in settings)")
        return False
    return _install()


def _install() -> bool:
    progress = xbmcgui.DialogProgressBG()
    progress.create(DIALOG_HEADING, "Preparing one-shot installation…")

    command = ["sudo", "-n", "/bin/bash", INSTALLER, ADDON_PATH]
    connect_utils.log("Running installer: {}".format(" ".join(command)))

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        progress.close()
        disable_connect_setting()
        xbmcgui.Dialog().ok(
            DIALOG_HEADING, "Could not start the installer:\n{}".format(exc)
        )
        return False

    last_message = "Installing…"
    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip()
            if not line:
                continue
            connect_utils.log("installer: {}".format(line))
            if line.startswith("@@"):
                try:
                    _, percent, message = line.split("@@", 2)
                    last_message = message
                    progress.update(max(0, min(100, int(percent))), message)
                except Exception:
                    progress.update(0, line)
            else:
                progress.update(0, last_message)
        returncode = process.wait()
    finally:
        progress.close()

    if returncode != 0:
        disable_connect_setting()
        if returncode == 77:
            detail = (
                "Kodi could not use passwordless sudo. Raspberry Pi OS normally "
                "permits this for the first user. Alternatively run once over SSH:\n"
                "sudo /bin/bash {} {}\n"
                "Spotify Connect has been disabled in the addon settings; "
                "re-enable it once the installation has succeeded.".format(
                    INSTALLER, ADDON_PATH
                )
            )
        else:
            detail = (
                "Installer exited with code {}. "
                "See /tmp/frankie-librespot-install.log.\n"
                "Spotify Connect has been disabled in the addon settings; "
                "re-enable it to retry.".format(returncode)
            )
        xbmcgui.Dialog().ok("Spotify Connect installation failed", detail)
        return False

    if ready():
        connect_utils.notification("This box is now available in Spotify Connect", time=8000)
        return True

    disable_connect_setting()
    xbmcgui.Dialog().ok(
        DIALOG_HEADING,
        "Installation completed, but the librespot binary is missing. "
        "See /tmp/frankie-librespot-install.log. Spotify Connect has been "
        "disabled in the addon settings; re-enable it to retry.",
    )
    return False
