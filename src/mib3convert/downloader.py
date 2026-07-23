"""Download videos from Yle Areena using the external `yle-dl` tool."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from .picker import VIDEO_EXTS

# Sidecar files yle-dl may write alongside the video (subs, metadata, art).
_NON_VIDEO_SUFFIXES = {".srt", ".vtt", ".ass", ".txt", ".json", ".xml", ".jpg", ".png", ".webp"}


class YleDlNotFound(RuntimeError):
    pass


class DownloadError(RuntimeError):
    pass


def _yle_base_cmd() -> list[str] | None:
    """How to invoke yle-dl. Prefers the bundled module over a PATH binary."""
    # yle-dl ships as the importable `yledl` package and is a dependency of
    # this app, so it's normally installed in the very same environment.
    if importlib.util.find_spec("yledl") is not None:
        return [sys.executable, "-m", "yledl"]
    exe = shutil.which("yle-dl")
    return [exe] if exe else None


def ensure_yle_dl() -> None:
    """Raise a friendly error if yle-dl is not available."""
    if _yle_base_cmd() is None:
        raise YleDlNotFound(
            "yle-dl is not available (needed to download from Yle Areena).\n"
            "It ships with this app; try reinstalling:  pipx install --force mib3convert\n"
            "Or add it manually:  pipx inject mib3convert yle-dl"
        )


def download_from_yle(url: str, destdir: Path) -> Path:
    """Download the given Yle Areena URL into destdir. Returns the video file.

    yle-dl's own progress is streamed straight to the terminal.
    """
    base = _yle_base_cmd()
    if base is None:
        raise YleDlNotFound("yle-dl is not available.")
    cmd = base + ["--destdir", str(destdir), url]
    try:
        result = subprocess.run(cmd)
    except OSError as exc:
        raise DownloadError(f"Could not run yle-dl: {exc}") from exc

    if result.returncode != 0:
        raise DownloadError(
            f"yle-dl exited with status {result.returncode}. "
            "Check the address and your connection (some content is Finland-only)."
        )

    files = [p for p in destdir.iterdir() if p.is_file()]
    videos = [p for p in files if p.suffix.lower() in VIDEO_EXTS]
    if not videos:
        # Fall back to anything that isn't an obvious sidecar file.
        videos = [p for p in files if p.suffix.lower() not in _NON_VIDEO_SUFFIXES]
    if not videos:
        raise DownloadError(
            "Download finished but no video file was found in the output."
        )
    # If several parts were written, take the largest.
    return max(videos, key=lambda p: p.stat().st_size)
