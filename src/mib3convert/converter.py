"""ffmpeg wrapper: probing + MIB3-targeted transcoding with live progress."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .profiles import Profile


class FFmpegNotFound(RuntimeError):
    pass


class ConversionError(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    """Raise a friendly error if ffmpeg/ffprobe are not on PATH."""
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise FFmpegNotFound(
            "Required tool(s) not found on PATH: "
            + ", ".join(missing)
            + ".\nInstall ffmpeg first, e.g.  sudo apt install ffmpeg  (Debian/Ubuntu)"
            "  |  brew install ffmpeg  (macOS)."
        )


@dataclass
class MediaInfo:
    duration: float  # seconds
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool
    v_codec: str | None
    a_codec: str | None
    pix_fmt: str | None = None
    v_profile: str | None = None
    v_level: int | None = None
    a_channels: int | None = None


def _parse_fraction(value: str) -> float | None:
    try:
        if "/" in value:
            num, den = value.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else None
        return float(value)
    except (ValueError, ZeroDivisionError):
        return None


def probe(path: Path) -> MediaInfo:
    """Read stream/format info via ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError as exc:
        raise ConversionError(
            f"ffprobe could not read '{path.name}'. Is it a valid media file?\n{exc.stderr.strip()}"
        ) from exc

    data = json.loads(out or "{}")
    duration = 0.0
    fmt = data.get("format", {})
    if fmt.get("duration") not in (None, "N/A"):
        try:
            duration = float(fmt["duration"])
        except ValueError:
            duration = 0.0

    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    fps = None
    if v:
        fps = _parse_fraction(v.get("avg_frame_rate", "0")) or _parse_fraction(
            v.get("r_frame_rate", "0")
        )
        # duration sometimes lives on the stream, not the container
        if duration == 0.0 and v.get("duration") not in (None, "N/A"):
            try:
                duration = float(v["duration"])
            except ValueError:
                pass

    v_level = None
    if v and v.get("level") not in (None, "N/A", -99):
        try:
            v_level = int(v["level"])
        except (ValueError, TypeError):
            v_level = None

    return MediaInfo(
        duration=duration,
        width=int(v["width"]) if v and v.get("width") else None,
        height=int(v["height"]) if v and v.get("height") else None,
        fps=fps,
        has_audio=a is not None,
        v_codec=v.get("codec_name") if v else None,
        a_codec=a.get("codec_name") if a else None,
        pix_fmt=v.get("pix_fmt") if v else None,
        v_profile=(v.get("profile") if v else None),
        v_level=v_level,
        a_channels=int(a["channels"]) if a and a.get("channels") else None,
    )


def _video_filters(profile: Profile, info: MediaInfo) -> str:
    w, h = profile.max_width, profile.max_height
    # Fit inside the WxH box, never upscale, keep aspect ratio, force even dims.
    filters = [
        f"scale=w='min(iw,{w})':h='min(ih,{h})':force_original_aspect_ratio=decrease",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
    ]
    if profile.fps_force:
        filters.append(f"fps={profile.fps_force}")
    elif profile.fps_cap and info.fps and info.fps > profile.fps_cap + 0.01:
        filters.append(f"fps={profile.fps_cap:g}")
    return ",".join(filters)


# Rank of H.264 profiles by feature set. A source may be stream-copied only if
# its profile is no higher than the target profile (e.g. copying a High-profile
# source into a Baseline target would keep the very features MIB3 can't decode).
_PROFILE_RANK = {
    "constrained baseline": 0,
    "baseline": 0,
    "main": 1,
    "high": 2,
}


def _level_ceiling(profile: Profile) -> int:
    """Profile.h264_level like '4.0' -> ffprobe integer level like 40."""
    try:
        return int(round(float(profile.h264_level) * 10))
    except ValueError:
        return 41


def video_can_copy(profile: Profile, info: MediaInfo) -> bool:
    """True when the source video already meets the target — no re-encode needed."""
    if profile.fps_force is not None:
        return False  # a forced fps always requires re-timing
    if info.v_codec != "h264" or info.pix_fmt != "yuv420p":
        return False
    if not info.width or not info.height:
        return False
    if info.width > profile.max_width or info.height > profile.max_height:
        return False
    if profile.fps_cap and info.fps and info.fps > profile.fps_cap + 0.01:
        return False
    # Source H.264 profile must be known and no higher than the target's.
    target_rank = _PROFILE_RANK.get(profile.h264_profile.lower())
    src_rank = _PROFILE_RANK.get((info.v_profile or "").lower())
    if target_rank is None or src_rank is None or src_rank > target_rank:
        return False
    if info.v_level and info.v_level > _level_ceiling(profile):
        return False
    return True


def audio_can_copy(profile: Profile, info: MediaInfo) -> bool:
    """True when the source audio is already stereo AAC — no re-encode needed."""
    if not info.has_audio:
        return False
    return info.a_codec == "aac" and info.a_channels == profile.audio_channels


def plan(profile: Profile, info: MediaInfo) -> tuple[bool, bool]:
    """Return (copy_video, copy_audio) for this source/profile."""
    return video_can_copy(profile, info), audio_can_copy(profile, info)


def build_command(src: Path, dst: Path, profile: Profile, info: MediaInfo) -> list[str]:
    copy_v, copy_a = plan(profile, info)

    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-i", str(src),
        "-map", "0:v:0",
    ]
    if info.has_audio:
        cmd += ["-map", "0:a:0"]

    if copy_v:
        cmd += ["-c:v", "copy"]
    else:
        cmd += [
            "-c:v", "libx264",
            "-profile:v", profile.h264_profile,
            "-level", profile.h264_level,
            "-pix_fmt", "yuv420p",
            "-preset", profile.preset,
            "-crf", str(profile.crf),
            "-vf", _video_filters(profile, info),
        ]

    if info.has_audio:
        if copy_a:
            cmd += ["-c:a", "copy"]
        else:
            cmd += [
                "-c:a", "aac",
                "-b:a", profile.audio_bitrate,
                "-ac", str(profile.audio_channels),
                "-ar", str(profile.audio_sample_rate),
            ]

    cmd += [
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-nostats",
        str(dst),
    ]
    return cmd


def _iter_progress(cmd: list[str]) -> Iterator[tuple[float, bool]]:
    """Run ffmpeg, yielding (elapsed_seconds, finished) as it encodes.

    Raises ConversionError with captured stderr if ffmpeg exits non-zero.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key in ("out_time_us", "out_time_ms"):  # both are microseconds in ffmpeg
            try:
                yield int(value) / 1_000_000, False
            except ValueError:
                continue
        elif key == "progress" and value == "end":
            yield 0.0, True

    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        tail = "\n".join(stderr.strip().splitlines()[-15:])
        raise ConversionError(f"ffmpeg failed:\n{tail}")


def convert(
    src: Path,
    dst: Path,
    profile: Profile,
    info: MediaInfo,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    """Transcode src -> dst. on_progress receives a 0..1 fraction."""
    cmd = build_command(src, dst, profile, info)
    total = info.duration or 0.0
    try:
        for elapsed, finished in _iter_progress(cmd):
            if on_progress is None:
                continue
            if finished:
                on_progress(1.0)
            elif total > 0:
                on_progress(min(elapsed / total, 0.999))
    except BaseException:
        # Don't leave a half-written file behind on failure / Ctrl-C.
        dst.unlink(missing_ok=True)
        raise
