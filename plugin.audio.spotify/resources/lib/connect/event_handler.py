"""UDP loopback receiver for librespot --onevent notifications.

Ported from service.librespot 12.3.1.0.
"""

import json
import socket
import threading

from . import onevent, utils

_BUFFER = 65535


class EventHandler:
    @utils.logged_method
    def __init__(self, target):
        self._target = target
        self._socket = socket.socket(onevent.SOCK_AF, onevent.SOCK_TYPE)
        self._socket.settimeout(None)
        self._socket.bind((onevent.HOST, 0))
        self._port = self._socket.getsockname()[1]
        self._receiver = threading.Thread(
            target=self._handle_events, name="librespot-events", daemon=True
        )
        self._receiver.start()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        onevent.send_event(self._port)
        self._receiver.join(timeout=5)
        try:
            self._socket.close()
        except Exception:
            pass

    def _handle_events(self):
        utils.log("Event handler listening on port {}".format(self._port))
        with self._socket:
            while True:
                data, _ = self._socket.recvfrom(_BUFFER)
                event, payload = json.loads(data)
                if not event:
                    break
                try:
                    utils.log("Event handler handling {}{}".format(event, payload))
                    method = "on_event_{}".format(event)
                    getattr(self._target, method)(**payload)
                except Exception as exc:
                    utils.log("Event handler failed to handle {}: {}".format(event, exc))
        utils.log("Event handler ended")

    def get_onevent(self):
        # librespot hands this to a shell; quote the path in case the Kodi
        # addon directory contains spaces.
        return '/usr/bin/python3 "{}" {}'.format(onevent.__file__, self._port)
