"""Spotify Connect session that plays through Kodi's player.

Ported from service.librespot 12.3.1.0 (there: resources/lib/service_kodi.py).
"""

from . import rtp_pump, session, utils


class Service(session.Service):
    """Plays Spotify inside Kodi with artwork, metadata and seek.

    Librespot's pipe backend writes raw PCM into a FIFO; RtpPump turns that
    into an L16 RTP stream on the loopback, and Kodi plays the rtp:// URL.
    Kodi remains the only process touching the ALSA device.
    """

    @utils.logged_method
    def __init__(self, zeroconf_port):
        self.pump = rtp_pump.RtpPump()
        super().__init__(
            "pipe",
            self.pump.get_fifo(),
            zeroconf_port,
            self.pump.get_file(),
        )

    def run(self):
        with self.pump:
            yield from super().run()

    def on_event_paused(self, **kwargs):
        self.player.do_paused(**kwargs)

    def on_event_playing(self, **kwargs):
        self.player.do_playing(**kwargs)

    def on_event_position_correction(self, **kwargs):
        self.player.do_seeked(**kwargs)

    def on_event_seeked(self, **kwargs):
        self.player.do_seeked(**kwargs)

    def on_event_stopped(self, **_):
        self.player.do_stopped()

    def on_event_track_changed(self, **kwargs):
        self.player.do_track_changed(**kwargs)
