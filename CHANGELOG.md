# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-11-24

### Added
- Standalone `casttv` repository extracted from `watchtv`.
- Live interactive single-key CLI playback controls (`Space`/`p` play/pause, `f`/`→` forward 30s, `r`/`←` rewind 30s, `+`/`-` volume, `m` mute, `i`/`s` status, `q`/`Ctrl+C` stop).
- One-shot `--ctl` / `-c` CLI control flag (`play`, `pause`, `toggle`, `stop`, `ffwd`, `rewind`, `seek`, `volume`, `volup`, `voldown`, `mute`, `status`, `info`).
- `--no-controls` flag to disable the live interactive key listener during casting.
- `requirements.txt` pinning `catt>=0.13.3`.

## [0.1.0] - 2026-11-24

### Added
- Initial standalone Chromecast CLI with `--scan`, `-m`/`--media`, `-d`/`--device`, `-s`/`--subtitles`, and clean `Ctrl+C` receiver stop teardown.
