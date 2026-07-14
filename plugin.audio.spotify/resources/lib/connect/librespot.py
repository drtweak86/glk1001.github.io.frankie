"""librespot process lifecycle for Spotify Connect.

Ported from service.librespot 12.3.1.0.
"""

import socket
import subprocess
import threading
import time

from . import utils


class Librespot:
    @utils.logged_method
    def __init__(self, target, backend, device, zeroconf_port):
        self._target = target
        self._backend = backend
        self._device = device
        self._zeroconf_port = str(zeroconf_port)
        self._process = None
        self._thread = None
        self._lock = threading.RLock()
        self._desired_running = False
        self._closing = False
        self._failures = 0
        self._max_failures = 5

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _command(self):
        name = utils.get_setting("connect_name").format(socket.gethostname())
        command = [
            utils.LIBRESPOT_BINARY,
            "--backend", self._backend,
            "--bitrate", "320",
            "--device", self._device,
            "--device-type", "tv",
            "--disable-audio-cache",
            "--disable-credential-cache",
            "--initial-volume", "100",
            "--name", name,
            "--onevent", self._target.event_handler.get_onevent(),
            "--quiet",
        ]
        if self._backend == "pipe":
            command.extend(["--format", "S16"])
        if self._zeroconf_port != "0":
            command.extend(["--zeroconf-port", self._zeroconf_port])
        return command

    def _spawn_locked(self):
        if self._closing or not self._desired_running:
            return
        if self._process is not None and self._process.poll() is None:
            return

        command = self._command()
        utils.log("Starting: {}".format(" ".join(command)))
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
            name="librespot-process",
            daemon=True,
        )
        self._thread.start()

    def _monitor(self, process):
        self._target.on_librespot_started()
        if process.stderr is not None:
            for line in process.stderr:
                utils.log(line.rstrip())
        returncode = process.wait()
        self._target.on_librespot_stopped()

        with self._lock:
            if self._process is process:
                self._process = None
            if self._closing or not self._desired_running:
                return
            if returncode < 0:
                self._failures = 0
            else:
                self._failures += 1
            if self._failures >= self._max_failures:
                utils.call_if_has(self._target, "on_librespot_broken")
                utils.log("Librespot crashed too many times")
                utils.notification("Librespot crashed too many times")
                self._desired_running = False
                return

        time.sleep(2)
        with self._lock:
            self._spawn_locked()

    @utils.logged_method
    def start(self):
        with self._lock:
            self._desired_running = True
            self._spawn_locked()

    @utils.logged_method
    def stop(self):
        with self._lock:
            self._desired_running = False
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    @utils.logged_method
    def restart(self):
        with self._lock:
            self._desired_running = True
            process = self._process
            if process is None or process.poll() is not None:
                self._spawn_locked()
                return
        process.terminate()

    @utils.logged_method
    def close(self):
        with self._lock:
            self._closing = True
            self._desired_running = False
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
