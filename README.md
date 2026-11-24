# casttv

![Version](https://img.shields.io/badge/version-0.4.0-blue.svg?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg?style=flat-square)

Lightweight CLI tool to cast local movies and subtitles directly to a Google Chromecast, with native macOS menu bar playback controls and clean teardown.

## Prerequisites

Install Python dependencies via [pip](https://pip.pypa.io):

```bash
pip3 install -r requirements.txt
```

> On macOS Sequoia+, ensure **Python** is allowed under **System Settings → Privacy & Security → Local Network**.

## Usage

```bash
# 1. Discover Chromecast devices on your Wi-Fi
./casttv.py --scan

# 2. Cast a movie (auto-detects Chromecast, matching subtitles, and opens macOS menu bar controls)
./casttv.py -m /path/to/movies/my-movie.mp4

# 3. Target a specific Chromecast or subtitle file
./casttv.py -m /path/to/movies/my-movie.mp4 -d "my_chromecast" -s /path/to/subtitles.srt

# 4. Cast without macOS menu bar (headless mode)
./casttv.py -m /path/to/movies/my-movie.mp4 --no-gui

# 5. Send one-shot playback commands from any terminal or script
./casttv.py --ctl toggle
./casttv.py --ctl ffwd 30
./casttv.py --ctl rewind 15
./casttv.py --ctl seek 12:30
./casttv.py --ctl status
./casttv.py --ctl stop

# 6. Manually stop an orphan connection or force disconnect a Chromecast
./casttv.py --ctl stop
./casttv.py -d "my_chromecast" --ctl stop
```

## macOS Menu Bar Controls

While casting, a **📺** icon appears in your top macOS menu bar with instant playback controls:

* 🎬 **Now Playing**: Displays currently playing video title
* 📡 **Device**: Displays target Chromecast device
* ⏯ **Play / Pause**
* ⏩ **Forward 10s** / ⏩ **Forward 30s**
* ⏪ **Rewind 10s** / ⏪ **Rewind 30s**
* 🔊 **Volume Up (+5%)** / 🔉 **Volume Down (-5%)** / 🔇 **Toggle Mute**
* 🛑 **Stop Casting**: Disconnects Chromecast receiver cleanly and shuts down the session

*(Use `--no-gui` to disable the menu bar app and run purely in headless CLI mode.)*

> [!TIP]
> **Stopping Orphan Sessions**: If a cast session was interrupted unexpectedly or the Chromecast is stuck buffering/playing, run `./casttv.py --ctl stop` (or `./casttv.py -d "device_name" --ctl stop`) from any terminal to immediately disconnect the receiver app and return the TV to its backdrop screen.

## Version History

| Version | Status | Highlights |
| :--- | :---: | :--- |
| **`v0.4.0`** | 🚀 *Latest* | Replaced interactive terminal controls with native macOS Menu Bar remote (`rumps`), added `--no-gui`. |
| **`v0.3.0`** | ✅ | Fixed reliable mute toggling with `catt volumemute` and added explicit `--ctl mute on/off`. |
| **`v0.2.0`** | ✅ | Added live interactive CLI keyboard remote & `--ctl` one-shot playback commands; extracted into standalone repo. |
| **`v0.1.0`** | ✅ | Initial standalone Chromecast CLI extracted from `watchtv` (`--scan`, `-s`, auto-discovery, clean stop). |

*(For full details, see [CHANGELOG.md](CHANGELOG.md))*
