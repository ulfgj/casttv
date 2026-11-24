#!/usr/bin/env python3
import argparse
import re
import select
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path

__version__ = "0.2.0"

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

# Single-key bindings active during live casting: key -> (catt args, label, show_output)
KEY_BINDINGS: dict[str, tuple[list[str], str, bool]] = {
    " ": (["play_toggle"], "Play / Pause", False),
    "p": (["play_toggle"], "Play / Pause", False),
    "f": (["ffwd", "30"], "Forward +30s", False),
    "r": (["rewind", "30"], "Rewind -30s", False),
    "+": (["volumeup"], "Volume +", False),
    "=": (["volumeup"], "Volume +", False),
    "-": (["volumedown"], "Volume -", False),
    "m": (["volumemute"], "Mute toggle", False),
    "i": (["status"], "Status", True),
    "s": (["status"], "Status", True),
}

ARROW_KEY_BINDINGS: dict[str, tuple[list[str], str]] = {
    "C": (["ffwd", "30"], "Forward +30s"),
    "D": (["rewind", "30"], "Rewind -30s"),
    "A": (["volumeup"], "Volume +"),
    "B": (["volumedown"], "Volume -"),
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
        "--no-controls",
        action="store_true",
        help="Disable interactive keyboard playback controls while casting.",
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


def build_catt_control_args(ctl_tokens: list[str]) -> list[str]:
    """Translate user-facing --ctl verb and optional arguments into catt CLI arguments."""
    verb = ctl_tokens[0].lower()
    extra = ctl_tokens[1:]

    if verb not in CTL_COMMANDS:
        supported = ", ".join(sorted(CTL_COMMANDS))
        raise ValueError(f"Unknown control command '{verb}'. Supported: {supported}")

    catt_cmd, defaults, requires_arg = CTL_COMMANDS[verb]
    if requires_arg and not extra:
        raise ValueError(f"Command '{verb}' requires an argument (e.g., --ctl {verb} 30).")

    args = extra if extra else defaults
    return [catt_cmd, *args]


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


def _handle_keypress(
    key: str,
    python_bin: str,
    target_device: str | None,
) -> bool:
    """Handle one keypress from the interactive remote. Return False to stop playback."""
    if key in {"q", "Q", "\x03"}:
        return False

    if key == "\x1b":
        # Parse ANSI arrow escape sequences (\x1b[A / B / C / D)
        if not select.select([sys.stdin], [], [], 0.05)[0]:
            return True
        if sys.stdin.read(1) != "[":
            return True
        if not select.select([sys.stdin], [], [], 0.05)[0]:
            return True
        arrow = sys.stdin.read(1)
        if arrow in ARROW_KEY_BINDINGS:
            catt_args, label = ARROW_KEY_BINDINGS[arrow]
            print(f"\r🎛️  {label}   ")
            run_cast_control(python_bin, target_device, catt_args, capture=True)
        return True

    if key in KEY_BINDINGS:
        catt_args, label, show_output = KEY_BINDINGS[key]
        res = run_cast_control(python_bin, target_device, catt_args, capture=True)
        if show_output:
            output = res.stdout.strip() or res.stderr.strip() or "No status available."
            print(f"\n📊 {output}\n")
        else:
            print(f"\r🎛️  {label}   ")
    return True


def interactive_control_loop(
    proc: subprocess.Popen[bytes] | subprocess.Popen[str],
    python_bin: str,
    target_device: str | None,
) -> None:
    """Listen for single-key playback commands while the catt streaming server runs."""
    print(
        "🎛️  Controls: [Space/p] Play/Pause | [f/→] +30s | [r/←] -30s | "
        "[+/-] Vol | [m] Mute | [i] Status | [q] Stop\n"
    )
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while proc.poll() is None:
            ready, _, _ = select.select([sys.stdin], [], [], 0.25)
            if not ready:
                continue
            key = sys.stdin.read(1)
            if not _handle_keypress(key, python_bin, target_device):
                print("\n🛑 Stopping Chromecast receiver...")
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def cast_media(
    video_path: Path,
    sub_file: Path | None,
    device: str | None = None,
    no_controls: bool = False,
) -> None:
    """Cast a video file and optional subtitles to a Google Chromecast using catt."""
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
    try:
        if sys.stdin.isatty() and not no_controls:
            interactive_control_loop(proc, python_bin, target_device)
        else:
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
        res = run_cast_control(sys.executable, target_device, catt_args, capture=False)
        sys.exit(res.returncode)

    if not args.media:
        print("Error: --media / -m is required unless --scan or --ctl is used.", file=sys.stderr)
        sys.exit(1)

    target_video = resolve_video_path(args.media)
    sub_file = resolve_subtitle_path(target_video, args.subtitles)
    cast_media(target_video, sub_file, device=args.device, no_controls=args.no_controls)


if __name__ == "__main__":
    main()
