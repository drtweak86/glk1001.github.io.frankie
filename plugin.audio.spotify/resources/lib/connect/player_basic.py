"""Minimal Kodi player for Spotify Connect: start playback, basic metadata.

Ported from service.librespot 12.3.1.0.
"""

import xbmcgui

from . import cover_art, player, utils


class Player(player.Player):
    @utils.logged_method
    def __init__(self, target, file, librespot):
        super().__init__(target, file, librespot)
        self._list_item = xbmcgui.ListItem(path=self.file)
        utils.set_inputstream_if_available(self._list_item)
        self._info_tag_music = self._list_item.getMusicInfoTag()

    def do_paused(self, **kwargs):
        self.do_playing(**kwargs)

    @utils.logged_method
    def do_playing(self, **_):
        if not self.is_playing_file():
            self.play(self.file, self._list_item)

    @utils.logged_method
    def do_track_changed(self, album="", art="", artist="", title="", **_):
        fanart = cover_art.get_fanart(art)
        artwork = {"thumb": art}
        if fanart:
            artwork["fanart"] = fanart
        self._list_item.setArt(artwork)
        self._info_tag_music.setAlbum(album)
        if artist:
            self._info_tag_music.setArtist(artist)
        self._info_tag_music.setTitle(title)
        if self.is_playing_file():
            self.updateInfoTag(self._list_item)
