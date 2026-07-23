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


# Native MIB3 panel is ~1540x720; 720p is a safe, universally accepted ceiling.
SAFE = Profile(
    name="safe",
    description="1280x720, keeps source fps up to 30, 192k stereo AAC. Good default.",
    max_width=1280,
    max_height=720,
    h264_profile="high",
    h264_level="4.0",
    crf=20,
    preset="medium",
    fps_force=None,
    fps_cap=30.0,
    audio_bitrate="192k",
    audio_sample_rate=48000,
    audio_channels=2,
)

# Matches the exact combo forum users found works on the pickiest units.
STRICT = Profile(
    name="strict",
    description="1280x720, forces 23.976 fps, 320k stereo AAC. Use if 'safe' greys out.",
    max_width=1280,
    max_height=720,
    h264_profile="high",
    h264_level="4.0",
    crf=20,
    preset="medium",
    fps_force="24000/1001",
    fps_cap=None,
    audio_bitrate="320k",
    audio_sample_rate=48000,
    audio_channels=2,
)

# Very old / low-end MIB units: keep it small and conservative.
COMPAT = Profile(
    name="compat",
    description="854x480, forces 23.976 fps, H.264 Main, 192k stereo AAC. Maximum compatibility.",
    max_width=854,
    max_height=480,
    h264_profile="main",
    h264_level="3.1",
    crf=21,
    preset="medium",
    fps_force="24000/1001",
    fps_cap=None,
    audio_bitrate="192k",
    audio_sample_rate=48000,
    audio_channels=2,
)

PROFILES = {p.name: p for p in (SAFE, STRICT, COMPAT)}
DEFAULT_PROFILE = SAFE.name
