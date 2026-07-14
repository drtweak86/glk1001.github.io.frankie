"""A Spotify Connect session: event handler + librespot + player.

Ported from service.librespot 12.3.1.0 (there: resources/lib/service.py).
run() is a generator entered by the ConnectManager; advancing or closing it
tears everything down via the context managers, so a settings change simply
resumes past the yield and rebuilds with fresh settings.
"""

import importlib

from . import event_handler, librespot, utils


class Service:
    @utils.logged_method
    def __init__(self, backend, device, zeroconf_port, file=""):
        self.backend = backend
        self.device = device
        self.zeroconf_port = zeroconf_port
        self.file = file

    @utils.logged_method
    def run(self):
        if self.file:
            player_name = utils.get_setting("connect_player")
            module_player = ".player_{}".format(player_name)
        else:
            module_player = ".player"
        player_module = importlib.import_module(module_player, __package__)

        with event_handler.EventHandler(self) as self.event_handler:
            with librespot.Librespot(
                self, self.backend, self.device, self.zeroconf_port
            ) as self.librespot:
                self.player = player_module.Player(self, self.file, self.librespot)
                try:
                    yield
                finally:
                    del self.player

    def on_event_paused(self, **_):
        pass

    def on_event_playing(self, **_):
        pass

    def on_event_position_correction(self, **_):
        pass

    def on_event_seeked(self, **_):
        pass

    def on_event_stopped(self, **kwargs):
        self.player.do_stopped(**kwargs)

    def on_event_track_changed(self, **kwargs):
        self.player.do_track_changed(**kwargs)

    def on_librespot_started(self):
        pass

    def on_librespot_stopped(self):
        pass

    def on_librespot_broken(self):
        utils.notification("Librespot stopped after repeated crashes")
