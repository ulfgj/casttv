# casttv

![Version](https://img.shields.io/badge/version-0.2.0-blue.svg?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg?style=flat-square)

Lightweight CLI tool to cast local movies and subtitles directly to a Google Chromecast, with built-in interactive keyboard playback controls and clean teardown.

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

# 2. Cast a movie (auto-detects Chromecast, matching .srt/.vtt subtitles, and opens live CLI controls)
./casttv.py -m /path/to/movies/my-movie.mp4

# 3. Target a specific Chromecast or subtitle file
./casttv.py -m /path/to/movies/my-movie.mp4 -d "my_chromecast" -s /path/to/subtitles.srt

# 4. Send one-shot playback commands from another terminal
./casttv.py --ctl toggle
./casttv.py --ctl ffwd 30
./casttv.py --ctl rewind 15
./casttv.py --ctl seek 12:30
./casttv.py --ctl status
./casttv.py --ctl stop
```

## Live Keyboard Controls

While casting from an interactive terminal, single keypresses control playback immediately:

| Key | Action |
| :--- | :--- |
| `Space` / `p` | Play / Pause |
| `f` / `→` | Fast-forward 30s |
| `r` / `←` | Rewind 30s |
| `+` / `-` (or `↑` / `↓`) | Volume up / down |
| `m` | Toggle mute |
| `i` / `s` | Print current playback status |
| `q` / `Ctrl+C` | Stop Chromecast receiver cleanly and exit |

*(Use `--no-controls` to disable the live key listener.)*

## Version History

| Version | Status | Highlights |
| :--- | :---: | :--- |
| **`v0.2.0`** | 🚀 *Latest* | Added live interactive CLI keyboard remote & `--ctl` one-shot playback commands; extracted into standalone repo. |
| **`v0.1.0`** | ✅ | Initial standalone Chromecast CLI extracted from `watchtv` (`--scan`, `-s`, auto-discovery, clean stop). |

*(For full details, see [CHANGELOG.md](CHANGELOG.md))*
