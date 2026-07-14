"""FIFO + ffmpeg bridge that turns librespot's pipe output into local RTP.

Ported from service.librespot 12.3.1.0.
"""

import os
import stat
import subprocess
import threading
import time

from . import utils

FFMPEG = "/usr/bin/ffmpeg"
ADDRESS = "127.0.0.1"
PORT = "23432"


class RtpPump:
    """Feeds librespot's raw PCM pipe into a local RTP stream for Kodi.

    librespot (pipe backend) writes S16LE 44.1 kHz stereo into a FIFO, ffmpeg
    re-wraps it as RTP payload type 10 (L16/44100/2) on the loopback
    interface, and Kodi plays rtp://127.0.0.1:23432.

    A keeper file descriptor holds the FIFO open read/write so librespot can
    open and close its end between sessions without ffmpeg ever seeing EOF.
    """

    @utils.logged_method
    def __init__(self):
        self._fifo = os.path.join(utils.ADDON_HOME, "librespot.fifo")
        self._file = "rtp://{}:{}".format(ADDRESS, PORT)
        self._keeper_fd = None
        self._process = None
        self._thread = None
        self._lock = threading.RLock()
        self._closing = False

        if os.path.exists(self._fifo) and not stat.S_ISFIFO(
            os.stat(self._fifo).st_mode
        ):
            os.remove(self._fifo)
        if not os.path.exists(self._fifo):
            os.mkfifo(self._fifo, 0o600)

        # Never lets the read side hit EOF, never reads itself.
        self._keeper_fd = os.open(self._fifo, os.O_RDWR)

        if not os.path.isfile(FFMPEG):
            raise RuntimeError(
                "{} is missing; reinstall the add-on dependencies".format(FFMPEG)
            )
        self._spawn_locked()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def get_fifo(self):
        return self._fifo

    def get_file(self):
        return self._file

    def _command(self):
        return [
            FFMPEG,
            "-hide_banner",
            "-nostdin",
            "-loglevel", "warning",
            # Raw PCM needs no probing; without these ffmpeg waits for a 5 MB
            # probe window that never completes (the keeper fd prevents EOF).
            "-probesize", "32",
            "-analyzeduration", "0",
            "-f", "s16le",
            "-ar", "44100",
            "-ac", "2",
            "-i", self._fifo,
            "-c:a", "pcm_s16be",
            "-f", "rtp",
            self._file,
        ]

    def _spawn_locked(self):
        if self._closing:
            return
        if self._process is not None and self._process.poll() is None:
            return

        command = self._command()
        utils.log("RTP pump starting: {}".format(" ".join(command)))
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        process = self._process
        self._thread = threading.Thread(
            target=self._monitor,
            args=(process,),
            name="librespot-rtp-pump",
            daemon=True,
        )
        self._thread.start()

    def _monitor(self, process):
        if process.stderr is not None:
            for line in process.stderr:
                utils.log("RTP pump: {}".format(line.rstrip()))
        returncode = process.wait()

        with self._lock:
            if self._process is process:
                self._process = None
            if self._closing:
                return
        utils.log("RTP pump exited with code {}; restarting".format(returncode))
        time.sleep(2)
        with self._lock:
            self._spawn_locked()

    @utils.logged_method
    def close(self):
        with self._lock:
            self._closing = True
            process = self._process
            thread = self._thread
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)
        if self._keeper_fd is not None:
            try:
                os.close(self._keeper_fd)
            except OSError:
                pass
            self._keeper_fd = None
        try:
            os.remove(self._fifo)
        except OSError:
            pass
