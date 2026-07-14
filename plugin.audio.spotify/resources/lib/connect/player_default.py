"""Full-featured Kodi player for Spotify Connect: metadata, artwork, seek.

Ported from service.librespot 12.3.1.0.
"""

import time

import xbmcgui

from . import cover_art, player, utils


class Player(player.Player):
    @utils.logged_method
    def __init__(self, target, file, librespot):
        super().__init__(target, file, librespot)
        self._list_item = xbmcgui.ListItem(path=self.file)
        utils.set_inputstream_if_available(self._list_item)
        self._info_tag_music = self._list_item.getMusicInfoTag()
        self._is_paused = False
        self._position = 0.0
        self._then = time.time()

    def _do_playing(self, paused, position=0.0, then=0.0, **_):
        self._is_paused = paused
        if self.is_playing_file():
            self.do_seeked(position, then)
        else:
            self._position = position
            self._then = then
            self.play(self.file, self._list_item)

    @utils.logged_method
    def do_paused(self, **kwargs):
        self._do_playing(True, **kwargs)

    @utils.logged_method
    def do_playing(self, **kwargs):
        self._do_playing(False, **kwargs)

    @utils.logged_method
    def do_seeked(self, position=0.0, then=0.0, **_):
        target = max(0.0, position if self._is_paused else position - then + time.time())
        if self.is_playing_file():
            self.seekTime(target)
            if self._is_paused and self.isPlayingAudio():
                self.pause()

    @utils.logged_method
    def do_track_changed(self, album="", art="", artist="", duration=0.0, title="", **_):
        fanart = cover_art.get_fanart(art)
        artwork = {"thumb": art}
        if fanart:
            artwork["fanart"] = fanart
        self._list_item.setArt(artwork)
        self._info_tag_music.setAlbum(album)
        if artist:
            self._info_tag_music.setArtist(artist)
        self._info_tag_music.setDuration(int(duration))
        self._info_tag_music.setTitle(title)
        if self.is_playing_file():
            self.updateInfoTag(self._list_item)

    @utils.logged_method
    def on_playback_started(self):
        self.do_seeked(self._position, self._then)
