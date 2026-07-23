"""Encoding profiles targeting VW MIB3 / MOI3 head units.

Community testing (Audizine, VW ID / T-Roc forums) shows MIB3 units reliably
play an MP4/H.264 + stereo AAC file, but silently *reject* (grey-out) files
that use a high frame rate (>~30 fps) or multichannel / 5.1 audio. 23.976 fps
constant with stereo AAC is the most broadly compatible combination.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    # Video
    max_width: int
    max_height: int
    h264_profile: str          # baseline / main / high
    h264_level: str            # e.g. "4.0"
    crf: int
    preset: str
    fps_force: str | None      # always re-time to this fps (e.g. "24000/1001")
    fps_cap: float | None      # only re-time when the source exceeds this
    # Audio
    audio_bitrate: str
    audio_sample_rate: int
    audio_channels: int


# MIB3 units reliably decode only H.264 *Baseline* (no CABAC, no B-frames);
# High/Main-profile streams often play audio with a black/absent picture. Every
# confirmed-working community config uses Baseline. Native panel is 1280x720 or
# 1540x720, so 720p is the ceiling. 23.976 fps constant is the safest rate
# (>=30 fps or 5.1 audio is a known cause of files being rejected/greyed out).
SAFE = Profile(
    name="safe",
    description="Baseline L3.1, 1280x720, 23.976 fps, stereo AAC. Recommended default.",
    max_width=1280,
    max_height=720,
    h264_profile="baseline",
    h264_level="3.1",
    crf=20,
    preset="veryfast",
    fps_force="24000/1001",
    fps_cap=None,
    audio_bitrate="192k",
    audio_sample_rate=48000,
    audio_channels=2,
)

# Same Baseline target, but keep the source frame rate (capped at 30). Use when
# forcing 23.976 makes 25/30 fps content look juddery.
SMOOTH = Profile(
    name="smooth",
    description="Baseline L3.1, 1280x720, keeps source fps up to 30, stereo AAC.",
    max_width=1280,
    max_height=720,
    h264_profile="baseline",
    h264_level="3.1",
    crf=20,
    preset="veryfast",
    fps_force=None,
    fps_cap=30.0,
    audio_bitrate="192k",
    audio_sample_rate=48000,
    audio_channels=2,
)

# Smallest / most conservative: for the oldest or pickiest units.
COMPAT = Profile(
    name="compat",
    description="Baseline L3.0, 854x480, 23.976 fps, stereo AAC. Maximum compatibility.",
    max_width=854,
    max_height=480,
    h264_profile="baseline",
    h264_level="3.0",
    crf=21,
    preset="veryfast",
    fps_force="24000/1001",
    fps_cap=None,
    audio_bitrate="192k",
    audio_sample_rate=48000,
    audio_channels=2,
)

PROFILES = {p.name: p for p in (SAFE, SMOOTH, COMPAT)}
DEFAULT_PROFILE = SAFE.name
