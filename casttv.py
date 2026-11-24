#!/usr/bin/env python3
import argparse
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

__version__ = "0.4.0"

# Optional rumps import for macOS menu bar controls
try:
    import rumps
    import rumps.rumps

    _orig_app_support = rumps.rumps.application_support

    def _safe_app_support(name: str) -> str:
        try:
            return _orig_app_support(name)
        except Exception:
            return f"/tmp/{name}"

    rumps.rumps.application_support = _safe_app_support
    HAS_RUMPS = True
except ImportError:
    HAS_RUMPS = False

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".m4v", ".webm", ".avi"}
SUBTITLE_EXTENSIONS = (".srt", ".vtt")

# Mapping from CLI --ctl verbs to (catt subcommand, default extra args, requires_arg)
CTL_COMMANDS: dict[str, tuple[str, list[str], bool]] = {
    "play": ("play", [], False),
    "pause": ("pause", [], False),
    "toggle": ("play_toggle", [], False),
    "play_toggle": ("play_toggle", [], False),
    "stop": ("stop", [], False),
    "ffwd": ("ffwd", ["30"], False),
    "forward": ("ffwd", ["30"], False),
    "rewind": ("rewind", ["30"], False),
    "back": ("rewind", ["30"], False),
    "seek": ("seek", [], True),
    "volume": ("volume", [], True),
    "volup": ("volumeup", [], False),
    "volumeup": ("volumeup", [], False),
    "voldown": ("volumedown", [], False),
    "volumedown": ("volumedown", [], False),
    "mute": ("volumemute", [], False),
    "volumemute": ("volumemute", [], False),
    "status": ("status", [], False),
    "info": ("info", [], False),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cast local video files and subtitles directly to a Google Chromecast."
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--media",
        "-m",
        type=str,
        default=None,
        help="Path to a movie file or a folder containing movies.",
    )
    parser.add_argument(
        "--device",
        "--cast-device",
        "-d",
        dest="device",
        type=str,
        default=None,
        help="Target Chromecast device name or IP (default: auto-detect).",
    )
    parser.add_argument(
        "--subtitles",
        "-s",
        type=str,
        default=None,
        help="Optional subtitle file (.srt or .vtt). Auto-detects matching file if omitted.",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Discover available Chromecast devices on the local network and exit.",
    )
    parser.add_argument(
        "--no-gui",
        "--headless",
        action="store_true",
        help="Disable macOS menu bar controls while casting.",
    )
    parser.add_argument(
        "--ctl",
        "-c",
        nargs="+",
        metavar="ARG",
        default=None,
        help=(
            "Send a one-shot playback command: play, pause, toggle, stop, "
            "ffwd [sec], rewind [sec], seek <time>, volume <0-100>, volup, voldown, mute, status."
        ),
    )
    return parser.parse_args()


def ensure_catt_installed() -> None:
    """Exit with installation instructions if 'catt' is unavailable."""
    try:
        import catt  # noqa: F401
    except ImportError:
        print("Error: 'catt' is not installed. Install it with: pip3 install catt", file=sys.stderr)
        sys.exit(1)


def _run_dns_sd(args: list[str], wait_seconds: float) -> str:
    """Run macOS dns-sd briefly and return captured stdout."""
    proc = subprocess.Popen(
        ["dns-sd", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    time.sleep(wait_seconds)
    proc.terminate()
    out, _ = proc.communicate()
    return out


def discover_cast_devices() -> list[dict[str, str]]:
    """Discover Chromecast devices on the local network via mDNS (dns-sd)."""
    devices: list[dict[str, str]] = []
    seen_instances: set[str] = set()

    try:
        browse_out = _run_dns_sd(["-B", "_googlecast._tcp", "."], wait_seconds=1.2)
        for line in browse_out.splitlines():
            if "_googlecast._tcp." not in line:
                continue
            instance = line.split("_googlecast._tcp.")[-1].strip()
            if not instance or instance in seen_instances:
                continue
            seen_instances.add(instance)

            lookup_out = _run_dns_sd(
                ["-L", instance, "_googlecast._tcp", "local."],
                wait_seconds=0.8,
            )
            friendly_name = instance
            model = "Chromecast"
            host_port = ""

            for l_line in lookup_out.splitlines():
                if "can be reached at " in l_line:
                    host_port = l_line.split("can be reached at ")[-1].split(" ")[0].strip()
                fn_match = re.search(r"\bfn=((?:\\.|[^ ])+)", l_line)
                if fn_match:
                    friendly_name = fn_match.group(1).replace(r"\ ", " ")
                md_match = re.search(r"\bmd=((?:\\.|[^ ])+)", l_line)
                if md_match:
                    model = md_match.group(1).replace(r"\ ", " ")

            devices.append(
                {
                    "name": friendly_name,
                    "model": model,
                    "host": host_port,
                    "instance": instance,
                }
            )
    except FileNotFoundError:
        return []
    except Exception:
        return devices

    return devices


def resolve_target_device(explicit_device: str | None) -> str | None:
    """Return explicit device name/IP or first discovered local Chromecast."""
    if explicit_device:
        return explicit_device
    discovered = discover_cast_devices()
    return discovered[0]["name"] if discovered else None


def resolve_video_path(raw_media: str) -> Path:
    """Resolve input path to a single playable video file."""
    input_path = Path(raw_media).expanduser().resolve()
    if not input_path.exists():
        print(f"Error: '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if input_path.is_file():
        return input_path

    video_files = sorted(
        f for f in input_path.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    )
    if not video_files:
        print(f"Error: No video files found in '{input_path}'.", file=sys.stderr)
        sys.exit(1)

    selected = video_files[0]
    if len(video_files) > 1:
        print(f"Multiple files in folder. Selecting: {selected.name}")
    return selected


def resolve_subtitle_path(video_path: Path, explicit_sub: str | None) -> Path | None:
    """Resolve explicit subtitle file or auto-detect matching .srt/.vtt sidecar."""
    if explicit_sub:
        sub_path = Path(explicit_sub).expanduser().resolve()
        if not sub_path.exists() or not sub_path.is_file():
            print(f"Error: Subtitle file '{sub_path}' does not exist.", file=sys.stderr)
            sys.exit(1)
        return sub_path

    for ext in SUBTITLE_EXTENSIONS:
        candidate = video_path.with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


def get_device_mute_status(python_bin: str, target_device: str | None) -> bool | None:
    """Query Chromecast status and return True if muted, False if unmuted, None if undetermined."""
    try:
        res = run_cast_control(python_bin, target_device, ["status"], capture=True)
        text = (res.stdout or "") + (res.stderr or "")
        match = re.search(r"Volume muted:\s*(True|False)", text, re.IGNORECASE)
        if match:
            return match.group(1).lower() == "true"
    except Exception:
        pass
    return None


def build_catt_control_args(ctl_tokens: list[str]) -> list[str]:
    """Translate user-facing --ctl verb and optional arguments into catt CLI arguments."""
    verb = ctl_tokens[0].lower()
    extra = ctl_tokens[1:]

    if verb not in CTL_COMMANDS:
        supported = ", ".join(sorted(CTL_COMMANDS))
        raise ValueError(f"Unknown control command '{verb}'. Supported: {supported}")

    if verb in ("mute", "volumemute"):
        if not extra:
            return ["volumemute", "toggle"]
        val = extra[0].lower()
        if val in ("1", "true", "t", "yes", "on"):
            return ["volumemute", "true"]
        if val in ("0", "false", "f", "no", "off"):
            return ["volumemute", "false"]
        if val == "toggle":
            return ["volumemute", "toggle"]
        raise ValueError(
            f"Invalid mute option '{extra[0]}'. Use 'on', 'off', or omit to toggle."
        )

    catt_cmd, defaults, requires_arg = CTL_COMMANDS[verb]
    if requires_arg and not extra:
        raise ValueError(f"Command '{verb}' requires an argument (e.g., --ctl {verb} 30).")

    args = extra if extra else defaults
    return [catt_cmd, *args]


def resolve_control_args(
    catt_args: list[str], python_bin: str, target_device: str | None
) -> list[str]:
    """Resolve dynamic control tokens (like 'toggle') into concrete arguments."""
    if len(catt_args) >= 2 and catt_args[0] == "volumemute" and catt_args[1] == "toggle":
        current_muted = get_device_mute_status(python_bin, target_device)
        new_val = "false" if current_muted is True else "true"
        return ["volumemute", new_val]
    return catt_args


def run_cast_control(
    python_bin: str,
    target_device: str | None,
    catt_args: list[str],
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Execute a catt playback control command against the target Chromecast."""
    cmd = [python_bin, "-m", "catt.cli"]
    if target_device:
        cmd.extend(["-d", target_device])
    cmd.extend(catt_args)

    return subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
        timeout=8,
    )


def send_chromecast_stop(python_bin: str, target_device: str | None) -> None:
    """Send an explicit stop signal so the Chromecast receiver exits cleanly instead of buffering."""
    try:
        run_cast_control(python_bin, target_device, ["stop"], capture=True)
    except Exception:
        pass


if HAS_RUMPS:

    class CastStatusBarApp(rumps.App):
        """macOS menu bar application for Chromecast playback control."""

        def __init__(
            self,
            video_name: str,
            device_name: str,
            python_bin: str,
            proc: subprocess.Popen[bytes] | subprocess.Popen[str],
            target_device: str | None,
        ) -> None:
            super().__init__("CastTV", title="📺", quit_button=None)
            self.video_name = video_name
            self.device_name = device_name
            self.python_bin = python_bin
            self.proc = proc
            self.target_device = target_device
            self.muted = False

            # Header items (read-only)
            self.header_title = rumps.MenuItem(f"🎬 {self.video_name}")
            self.header_device = rumps.MenuItem(f"📡 {self.device_name}")

            self.menu = [
                self.header_title,
                self.header_device,
                None,
                rumps.MenuItem("⏯  Play / Pause", callback=self.on_play_toggle),
                rumps.MenuItem("⏩  Forward 10s", callback=self.on_forward_10),
                rumps.MenuItem("⏩  Forward 30s", callback=self.on_forward_30),
                rumps.MenuItem("⏪  Rewind 10s", callback=self.on_rewind_10),
                rumps.MenuItem("⏪  Rewind 30s", callback=self.on_rewind_30),
                None,
                rumps.MenuItem("🔊  Volume Up (+5%)", callback=self.on_volume_up),
                rumps.MenuItem("🔉  Volume Down (-5%)", callback=self.on_volume_down),
                rumps.MenuItem("🔇  Toggle Mute", callback=self.on_toggle_mute),
                None,
                rumps.MenuItem("🛑  Stop Casting", callback=self.on_stop),
            ]

            self.muted = False

            # Monitor background catt process; quit menu bar once playback ends
            self.timer = rumps.Timer(self.on_tick, 1.5)
            self.timer.start()

        def on_tick(self, _sender: object) -> None:
            if self.proc.poll() is not None:
                self.timer.stop()
                rumps.quit_application()

        def on_play_toggle(self, _sender: object) -> None:
            run_cast_control(self.python_bin, self.target_device, ["play_toggle"], capture=True)

        def on_forward_10(self, _sender: object) -> None:
            run_cast_control(self.python_bin, self.target_device, ["ffwd", "10"], capture=True)

        def on_forward_30(self, _sender: object) -> None:
            run_cast_control(self.python_bin, self.target_device, ["ffwd", "30"], capture=True)

        def on_rewind_10(self, _sender: object) -> None:
            run_cast_control(self.python_bin, self.target_device, ["rewind", "10"], capture=True)

        def on_rewind_30(self, _sender: object) -> None:
            run_cast_control(self.python_bin, self.target_device, ["rewind", "30"], capture=True)

        def on_volume_up(self, _sender: object) -> None:
            run_cast_control(self.python_bin, self.target_device, ["volumeup"], capture=True)

        def on_volume_down(self, _sender: object) -> None:
            run_cast_control(self.python_bin, self.target_device, ["volumedown"], capture=True)

        def on_toggle_mute(self, _sender: object) -> None:
            self.muted = not self.muted
            arg = "true" if self.muted else "false"
            run_cast_control(
                self.python_bin, self.target_device, ["volumemute", arg], capture=True
            )

        def on_stop(self, _sender: object) -> None:
            self.timer.stop()
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            send_chromecast_stop(self.python_bin, self.target_device)
            rumps.quit_application()


def cast_media(
    video_path: Path,
    sub_file: Path | None,
    device: str | None = None,
    no_gui: bool = False,
) -> None:
    """Cast a video file and optional subtitles to a Google Chromecast."""
    python_bin = sys.executable
    target_device = resolve_target_device(device)

    cmd = [python_bin, "-m", "catt.cli"]
    if target_device:
        cmd.extend(["-d", target_device])

    cmd.append("cast")
    if sub_file:
        print(f"💬 Subtitle track: {sub_file.name}")
        cmd.extend(["-s", str(sub_file)])

    cmd.append(str(video_path))

    target_desc = f"device '{target_device}'" if target_device else "Chromecast"
    print(f"🎬 Casting '{video_path.name}' to {target_desc}...")

    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
    use_gui = HAS_RUMPS and not no_gui

    def _sigint_handler(_sig: int, _frame: object) -> None:
        print("\n🛑 Interrupt received! Stopping Chromecast receiver...")
        if use_gui:
            try:
                rumps.quit_application()
            except Exception:
                pass
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        send_chromecast_stop(python_bin, target_device)
        print("✅ Chromecast session stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        if use_gui:
            print("🎛️  macOS menu bar controls active (click 📺 in your top menu bar).")
            print("📺 Press Ctrl+C in terminal or click 'Stop Casting' in the menu bar to exit.\n")
            dev_label = target_device or "Chromecast"
            app = CastStatusBarApp(video_path.name, dev_label, python_bin, proc, target_device)
            app.run()
        else:
            if not HAS_RUMPS and not no_gui:
                print("💡 Note: 'rumps' is not installed. Install with: pip3 install rumps")
            print("📺 Playback started! Press Ctrl+C to stop casting.\n")
            proc.wait()
    except KeyboardInterrupt:
        print("\n🛑 Interrupt received! Stopping Chromecast receiver...")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        send_chromecast_stop(python_bin, target_device)
        print("✅ Chromecast session stopped.")


def main() -> None:
    args = parse_args()

    if args.scan:
        print("🔍 Scanning local network for Chromecast devices...")
        devices = discover_cast_devices()
        if not devices:
            print("No Chromecast devices found via mDNS.")
            sys.exit(1)
        for idx, dev in enumerate(devices, start=1):
            host_info = f" ({dev['host']})" if dev["host"] else ""
            print(f"[{idx}] {dev['name']} - {dev['model']}{host_info}")
        return

    ensure_catt_installed()

    if args.ctl:
        try:
            catt_args = build_catt_control_args(args.ctl)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        target_device = resolve_target_device(args.device)
        resolved_catt_args = resolve_control_args(catt_args, sys.executable, target_device)
        res = run_cast_control(sys.executable, target_device, resolved_catt_args, capture=False)
        sys.exit(res.returncode)

    if not args.media:
        print("Error: --media / -m is required unless --scan or --ctl is used.", file=sys.stderr)
        sys.exit(1)

    target_video = resolve_video_path(args.media)
    sub_file = resolve_subtitle_path(target_video, args.subtitles)
    cast_media(target_video, sub_file, device=args.device, no_gui=args.no_gui)


if __name__ == "__main__":
    main()
