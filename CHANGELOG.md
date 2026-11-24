# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-11-24

### Added
- **macOS Menu Bar Controls**: Integrated `rumps` status bar item (📺) displayed in the top macOS menu bar during casting. Features instant controls for Play/Pause, Forward 10s/30s, Rewind 10s/30s, Volume Up/Down, Mute Toggle, and Clean Stop.
- `--no-gui` / `--headless` CLI flag to optionally run without the menu bar item.
- Added `rumps>=0.4.0` dependency to `requirements.txt`.

### Removed
- **CLI Keyboard Remote**: Removed `termios`, `tty`, and `select` interactive terminal keyboard listener (`interactive_control_loop`, `_handle_keypress`, `KEY_BINDINGS`, `ARROW_KEY_BINDINGS`, and `--no-controls` flag), eliminating terminal hijacking during casting.

## [0.3.0] - 2026-11-24

### Fixed
- **Mute Toggle**: Fixed issue where pressing `m` in interactive mode or running `--ctl mute` only enabled mute without toggling back. `catt volumemute` requires an explicit boolean argument; `casttv` now tracks mute state and inspects device status to reliably toggle between mute (`true`) and unmute (`false`).
- **One-Shot Mute Options**: Added support for explicit `--ctl mute on` and `--ctl mute off` as well as argument-less `--ctl mute` auto-toggle.

## [0.2.0] - 2026-11-24

### Added
- Standalone `casttv` repository extracted from `watchtv`.
- Live interactive single-key CLI keyboard remote (`Space`/`p` play/pause, `f`/`→` forward 30s, `r`/`←` rewind 30s, `+`/`-` volume, `m` mute, `i`/`s` status, `q`/`Ctrl+C` stop).
- One-shot `--ctl` / `-c` CLI control flag (`play`, `pause`, `toggle`, `stop`, `ffwd`, `rewind`, `seek`, `volume`, `volup`, `voldown`, `mute`, `status`, `info`).
- `--no-controls` flag to disable the live interactive key listener during casting.
- `requirements.txt` pinning `catt>=0.13.3`.

## [0.1.0] - 2026-11-24

### Added
- Initial standalone Chromecast CLI with `--scan`, `-m`/`--media`, `-d`/`--device`, `-s`/`--subtitles`, and clean `Ctrl+C` receiver stop teardown.
