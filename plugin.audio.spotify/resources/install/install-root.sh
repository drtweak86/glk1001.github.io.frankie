#!/bin/bash
# One-shot root installer for the Spotify Connect (librespot) feature of
# plugin.audio.spotify on Raspberry Pi OS (Lite), ALSA edition.
#
# Provides librespot 0.8.0 with the ALSA + pipe backends and built-in libmdns
# zeroconf discovery. Playback inside Kodi is provided by ffmpeg re-wrapping
# librespot's pipe output as local RTP — no PulseAudio and no extra systemd
# services.
#
# The librespot binary is preferably taken prebuilt from the Raspotify
# project's Debian package (which bundles exactly librespot v0.8.0-d36f9f1,
# the commit pinned below). The package is only unpacked, never installed —
# installing it would add a competing raspotify systemd service. If no usable
# prebuilt binary can be downloaded, librespot is compiled from source.
#
# The binary and marker paths are shared with the standalone service.librespot
# addon so a box that already ran that addon skips installation entirely.
# Reruns are idempotent and skip acquisition when a matching binary exists.
set -Eeuo pipefail

LOG=/tmp/frankie-librespot-install.log
exec > >(tee -a "$LOG") 2>&1

progress() {
    printf '@@%s@@%s\n' "$1" "$2"
}

fail() {
    echo "ERROR: $*"
    exit 1
}

trap 'echo "ERROR at line $LINENO: $BASH_COMMAND"' ERR

[ "$(id -u)" -eq 0 ] || exit 77
[ $# -eq 1 ] || fail "Expected add-on path"
ADDON_PATH=$1
[ -d "$ADDON_PATH" ] || fail "Add-on path not found: $ADDON_PATH"

BINARY=/usr/local/bin/librespot-frankie
MARKER_DIR=/var/lib/frankie-librespot
MARKER=$MARKER_DIR/installed-0.8.0-alsa-r2
EXPECTED_COMMIT="d36f9f1907e8cc9d68a93f8ebc6b627b1bf7267d"
BINARY_SOURCE="existing"

TARGET_USER=${SUDO_USER:-}
if [ -z "$TARGET_USER" ] || ! id "$TARGET_USER" >/dev/null 2>&1; then
    TARGET_USER=$(getent passwd 1000 | cut -d: -f1)
fi
[ -n "$TARGET_USER" ] || fail "Could not determine the user that runs Kodi"
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
[ -n "$TARGET_HOME" ] || fail "No home directory for $TARGET_USER"
TARGET_GROUP=$(id -gn "$TARGET_USER")

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

progress 2 "Checking the system architecture"
DPKG_ARCH=$(dpkg --print-architecture)
case "$DPKG_ARCH" in
    armhf)
        RUST_TRIPLE=armv7-unknown-linux-gnueabihf
        ;;
    arm64)
        RUST_TRIPLE=aarch64-unknown-linux-gnu
        ;;
    *)
        fail "Unsupported architecture: $DPKG_ARCH (expected armhf or arm64 Raspberry Pi OS)"
        ;;
esac
echo "Architecture: $DPKG_ARCH -> $RUST_TRIPLE"

progress 4 "Making sure $TARGET_USER can use ALSA"
if ! id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx audio; then
    usermod -aG audio "$TARGET_USER"
    echo "Added $TARGET_USER to the audio group (takes effect after re-login/reboot)"
fi

progress 6 "Updating package lists"
apt-get update

progress 10 "Installing runtime dependencies (ffmpeg for the Kodi RTP bridge)"
apt-get install -y --no-install-recommends \
    ca-certificates curl ffmpeg python3-pil alsa-utils

# Downloads the Raspotify Debian package, unpacks it (never installs it) and
# installs just its librespot binary. Returns non-zero if no URL yielded a
# working librespot 0.8.0 for this machine.
install_prebuilt() {
    local deb_dir deb extracted url
    deb_dir=$(mktemp -d) || return 1
    deb="$deb_dir/raspotify.deb"
    extracted="$deb_dir/x/usr/bin/librespot"

    # Raspotify targets Debian Stable; its current packages bundle librespot
    # v0.8.0-d36f9f1. If a future Raspotify moves past 0.8.0, the version
    # check below rejects it and the source build takes over.
    for url in \
        "https://github.com/dtcooper/raspotify/releases/latest/download/raspotify-latest_${DPKG_ARCH}.deb" \
        "https://dtcooper.github.io/raspotify/raspotify-latest_${DPKG_ARCH}.deb"; do
        echo "Trying prebuilt librespot from: $url"
        rm -rf "$deb_dir/x"
        if ! curl --proto '=https' --tlsv1.2 -fL --connect-timeout 15 --max-time 300 \
                "$url" -o "$deb"; then
            echo "Download failed: $url"
            continue
        fi
        if ! dpkg-deb -x "$deb" "$deb_dir/x"; then
            echo "Could not unpack the Raspotify package"
            continue
        fi
        if [ ! -f "$extracted" ]; then
            echo "The Raspotify package did not contain usr/bin/librespot"
            continue
        fi
        chmod 755 "$extracted"
        if ! "$extracted" --version 2>/dev/null | grep -q '0\.8\.0'; then
            echo "Prebuilt librespot is not version 0.8.0:"
            "$extracted" --version 2>/dev/null || echo "(binary did not run)"
            continue
        fi
        if ldd "$extracted" | grep -q 'not found'; then
            echo "Prebuilt librespot has missing shared libraries:"
            ldd "$extracted"
            continue
        fi
        install -m 755 "$extracted" "$BINARY"
        strip "$BINARY" || true
        rm -rf "$deb_dir"
        return 0
    done

    rm -rf "$deb_dir"
    return 1
}

NEED_BINARY=1
if [ -x "$BINARY" ] && "$BINARY" --version 2>/dev/null | grep -q '0\.8\.0'; then
    echo "Existing librespot 0.8.0 binary found; skipping download and compilation"
    NEED_BINARY=0
fi

if [ "$NEED_BINARY" -eq 1 ]; then
    progress 14 "Downloading prebuilt librespot 0.8.0 (Raspotify package)"
    if install_prebuilt; then
        echo "Installed prebuilt librespot from the Raspotify package"
        BINARY_SOURCE="prebuilt-raspotify"
        NEED_BINARY=0
    else
        echo "No usable prebuilt librespot; falling back to compiling from source"
    fi
fi

if [ "$NEED_BINARY" -eq 1 ]; then
    BINARY_SOURCE="source-build"
    progress 20 "Installing build dependencies"
    apt-get install -y --no-install-recommends \
        curl git build-essential pkg-config cmake clang libclang-dev \
        protobuf-compiler libssl-dev libasound2-dev

    progress 24 "Installing the Rust compiler for $RUST_TRIPLE"
    RUSTUP_INIT=/tmp/rustup-init-frankie
    curl --proto '=https' --tlsv1.2 -fL \
        "https://static.rust-lang.org/rustup/dist/${RUST_TRIPLE}/rustup-init" \
        -o "$RUSTUP_INIT"
    chmod 755 "$RUSTUP_INIT"

    sudo -u "$TARGET_USER" env \
        HOME="$TARGET_HOME" \
        CARGO_HOME="$TARGET_HOME/.cargo" \
        RUSTUP_HOME="$TARGET_HOME/.rustup" \
        "$RUSTUP_INIT" -y --profile minimal --default-toolchain 1.89.0 --no-modify-path

    CARGO="$TARGET_HOME/.cargo/bin/cargo"
    RUSTC="$TARGET_HOME/.cargo/bin/rustc"
    [ -x "$CARGO" ] || fail "Cargo was not installed"

    HOST=$(
        sudo -u "$TARGET_USER" env HOME="$TARGET_HOME" \
            CARGO_HOME="$TARGET_HOME/.cargo" RUSTUP_HOME="$TARGET_HOME/.rustup" \
            "$RUSTC" -vV | awk '/^host:/ {print $2}'
    )
    [ "$HOST" = "$RUST_TRIPLE" ] || fail "Rust host is $HOST, expected $RUST_TRIPLE"

    progress 30 "Downloading librespot 0.8.0"
    BUILD_ROOT="$TARGET_HOME/.cache/frankie-librespot-build"
    rm -rf "$BUILD_ROOT"
    install -d -o "$TARGET_USER" -g "$TARGET_GROUP" "$BUILD_ROOT"

    sudo -u "$TARGET_USER" env HOME="$TARGET_HOME" git clone \
        --depth 1 --branch v0.8.0 \
        https://github.com/librespot-org/librespot.git "$BUILD_ROOT/librespot"

    COMMIT=$(sudo -u "$TARGET_USER" git -C "$BUILD_ROOT/librespot" rev-parse HEAD)
    [ "$COMMIT" = "$EXPECTED_COMMIT" ] || fail "Unexpected librespot v0.8.0 commit: $COMMIT"

    progress 35 "Compiling librespot (ALSA + pipe) — this is the slow part"
    sudo -u "$TARGET_USER" env \
        HOME="$TARGET_HOME" \
        CARGO_HOME="$TARGET_HOME/.cargo" \
        RUSTUP_HOME="$TARGET_HOME/.rustup" \
        CARGO_BUILD_JOBS=4 \
        nice -n 5 "$CARGO" build \
            --manifest-path "$BUILD_ROOT/librespot/Cargo.toml" \
            --release --locked --no-default-features \
            --features 'alsa-backend native-tls'

    BUILT="$BUILD_ROOT/librespot/target/release/librespot"
    [ -x "$BUILT" ] || fail "Compiled librespot binary was not produced"

    progress 82 "Installing the librespot binary"
    install -m 755 "$BUILT" "$BINARY"
    strip "$BINARY" || true
fi

"$BINARY" --version
if ldd "$BINARY" | grep -q 'not found'; then
    ldd "$BINARY"
    fail "The librespot binary has missing shared libraries"
fi

progress 90 "Checking the ALSA device list"
sudo -u "$TARGET_USER" aplay -L | head -n 20 || true

progress 94 "Writing installation marker"
install -d -m 755 "$MARKER_DIR"
cat > "$MARKER" <<EOF
librespot=0.8.0
commit=$EXPECTED_COMMIT
architecture=$DPKG_ARCH
backends=pipe+alsa
kodi_bridge=ffmpeg-rtp
binary_source=$BINARY_SOURCE
installed=$(date --iso-8601=seconds)
addon=$ADDON_PATH
EOF
chmod 644 "$MARKER"

progress 97 "Cleaning temporary build files"
rm -rf "${BUILD_ROOT:-}" "${RUSTUP_INIT:-}" 2>/dev/null || true

progress 100 "librespot is installed — this box is joining Spotify Connect"
echo "Installation complete"
