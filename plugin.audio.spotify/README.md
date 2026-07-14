# plugin.audio.spotify
Unofficial spotify plugin for Kodi, (for now) not yet available in the official Kodi repo.

Uses 'bottle' and 'librespot - spotty' for playback, and 'spotipy' for the playlist, albums, etc. menus.

Thanks to mherger for creating the special ['spotty'](https://github.com/michaelherger/librespot) branch forked off librespot.

This a fork of the [marcelveldt](https://github.com/marcelveldt) version, modified to work with Kodi 19 and 20.
Thanks to Ldsz, Elkropac, and FernetMenta for getting it to work with Python 3.9+.

## Spotify Connect (built-in, Linux only)
Starting with v1.4.0 this addon can also act as a persistent Spotify Connect
target: pick this device from the Spotify app on your phone and audio plays
through Kodi's own player, with metadata and artwork, alongside the existing
menu browse/play feature (which is unchanged).

- Ported from a standalone `service.librespot` add-on: `librespot --backend pipe`
  writes PCM into a FIFO, `ffmpeg` re-wraps it as local RTP
  (`rtp://127.0.0.1:23432`), and Kodi plays that URL. A `--onevent` hook keeps
  now-playing metadata in sync.
- Gated to Linux (e.g. Raspberry Pi OS); disabled automatically elsewhere.
- Enabled by default on Linux. The first time the service starts, a
  confirmation dialog appears before anything runs with `sudo` — declining
  turns the "Enable Spotify Connect" setting back off.
- The one-shot installer (`resources/install/install-root.sh`) first tries a
  prebuilt `librespot` 0.8.0 binary (from the Raspotify project's Debian
  package, unpacked — not installed, to avoid a competing service), and falls
  back to compiling from source if no matching prebuilt binary is available.
- If you previously used the standalone `service.librespot` add-on, **disable
  or uninstall it** before enabling this feature: both use the same librespot
  binary path/marker (so no re-install is needed) but must not run at the
  same time, since they'd fight over the RTP port and ALSA. Any leftover
  `addon_data/service.librespot/` files are harmless and can be deleted.
- Settings are under the "Spotify Connect" category: device name (defaults to
  the machine's hostname), output (`kodi` plays inside Kodi, `alsa` plays
  directly to the sound card), player mode, ALSA device, do-not-disturb, and
  Zeroconf options.
- The addon's own Spotify authentication (the "Kodi-Spotty" zeroconf device)
  automatically pauses Spotify Connect for the duration of the auth flow so
  the two don't announce competing Connect devices at once.

## Support
Create issue in Github.
