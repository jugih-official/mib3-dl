"""Command-line entry point for mib3-dl."""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from . import __version__
from .converter import (
    ConversionError,
    FFmpegNotFound,
    MediaInfo,
    convert,
    ensure_ffmpeg,
    plan,
    probe,
)
from .downloader import (
    DownloadError,
    YleDlNotFound,
    download_from_yle,
    ensure_yle_dl,
)
from .menu import choose
from .picker import pick_directory, pick_video
from .profiles import DEFAULT_PROFILE, PROFILES

console = Console()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mib3-dl",
        description="Convert virtually any video into a VW MIB3 / MOI3 friendly MP4.",
    )
    p.add_argument(
        "input",
        nargs="?",
        help="Input video file. If omitted, a terminal file picker opens.",
    )
    p.add_argument(
        "-o", "--output",
        help="Output file (default: <input>_mib3.mp4 next to the input).",
    )
    p.add_argument(
        "-p", "--profile",
        choices=list(PROFILES),
        default=DEFAULT_PROFILE,
        help="Encoding profile (default: %(default)s).",
    )
    p.add_argument(
        "--preset",
        choices=[
            "ultrafast", "superfast", "veryfast", "faster", "fast",
            "medium", "slow", "slower", "veryslow",
        ],
        help="x264 speed/quality preset, overriding the profile "
             "(faster = quicker but larger files).",
    )
    p.add_argument(
        "--path",
        default=".",
        help="Directory the file picker searches (default: current directory).",
    )
    p.add_argument(
        "--list-profiles",
        action="store_true",
        help="Show the available profiles and exit.",
    )
    p.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Overwrite the output file without asking.",
    )
    p.add_argument("--version", action="version", version=f"mib3-dl {__version__}")
    return p


def _print_profiles() -> None:
    table = Table(title="MIB3 / MOI3 encoding profiles")
    table.add_column("Profile", style="cyan bold")
    table.add_column("Description")
    for prof in PROFILES.values():
        marker = " (default)" if prof.name == DEFAULT_PROFILE else ""
        table.add_row(prof.name + marker, prof.description)
    console.print(table)


def _show_source(info: MediaInfo, src: Path) -> None:
    res = f"{info.width}x{info.height}" if info.width else "?"
    fps = f"{info.fps:.3f}".rstrip("0").rstrip(".") if info.fps else "?"
    dur = f"{info.duration:.0f}s" if info.duration else "?"
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("File", src.name)
    table.add_row("Video", f"{info.v_codec or '?'}  {res}  {fps} fps")
    table.add_row("Audio", info.a_codec or "none")
    table.add_row("Duration", dur)
    console.print(Panel(table, title="Source", expand=False, border_style="dim"))


# Characters that are illegal in FAT32 / exFAT filenames — the formats VW head
# units require on a USB stick. Yle programme titles routinely contain ':'
# (e.g. "Tuuri: Vauvakisa: 2026-06-27T08:14"), which makes the file impossible
# to create on the stick, so auto-generated names are always sanitised.
_ILLEGAL_FS_CHARS = '<>:"/\\|?*'
_MAX_STEM = 120


def safe_filename(stem: str, fallback: str = "video") -> str:
    """Turn a title into a filename that FAT32/exFAT (and NTFS) will accept."""
    cleaned = "".join(
        "-" if (ch in _ILLEGAL_FS_CHARS or ord(ch) < 32) else ch for ch in stem
    )
    # Collapse dash/space clusters: "Tuuri- Vauvakisa- 2026" -> "Tuuri-Vauvakisa-2026"
    cleaned = re.sub(r"[-\s]*-[-\s]*", "-", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    # FAT and Windows disallow trailing dots/spaces.
    cleaned = cleaned.strip(" .-")
    if len(cleaned) > _MAX_STEM:
        cleaned = cleaned[:_MAX_STEM].rstrip(" .-")
    return cleaned or fallback


def _default_output(src: Path) -> Path:
    return src.with_name(f"{safe_filename(src.stem)}_mib3.mp4")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.list_profiles:
        _print_profiles()
        return 0

    try:
        ensure_ffmpeg()
    except FFmpegNotFound as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    # --- resolve input ---------------------------------------------------
    # `auto` skips all remaining prompts (used for the Yle download flow).
    # `temp_dir` holds a downloaded original that we clean up at the end.
    auto = False
    temp_dir: Path | None = None
    out_dir: Path | None = None
    try:
        if args.input:
            src = Path(args.input).expanduser()
            if not src.is_file():
                console.print(f"[red]Input file not found:[/red] {src}")
                return 2
        else:
            source = choose(
                "Where is the video?",
                [
                    ("Yle Areena  (download by address)", "yle"),
                    ("Local file  (browse this computer)", "local"),
                ],
            )
            if source is None:
                console.print("[yellow]Cancelled.[/yellow]")
                return 1

            if source == "yle":
                url = _prompt_yle_url()
                if isinstance(url, int):
                    return url
                # Ask for the destination *before* downloading, so the
                # download + conversion still run unattended afterwards.
                out_dir = _choose_output_dir(args, Path.cwd())
                if out_dir is None and not args.output:
                    console.print("[yellow]Cancelled.[/yellow]")
                    return 1
                rc = _download_yle(url)
                if isinstance(rc, int):
                    return rc
                src, temp_dir = rc
                auto = True  # download → convert, no further questions
            else:
                search_root = Path(args.path).expanduser().resolve()
                picked = pick_video(search_root)
                if picked is None:
                    console.print("[yellow]No file selected.[/yellow]")
                    return 1
                src = picked
                out_dir = _choose_output_dir(args, src.parent)
                if out_dir is None and not args.output:
                    console.print("[yellow]Cancelled.[/yellow]")
                    return 1

        return _run_conversion(args, src, auto, out_dir)
    except KeyboardInterrupt:
        console.print("[yellow]Cancelled.[/yellow]")
        return 130
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)

def _choose_output_dir(args: argparse.Namespace, start: Path) -> Path | None:
    """Ask where to save the result. None means cancelled (or not asked)."""
    if args.output:
        return None  # an explicit -o wins; don't ask
    return pick_directory(start)


def _prompt_yle_url() -> str | int:
    """Prompt for a Yle Areena URL. Returns the URL or an exit code."""
    import questionary

    try:
        ensure_yle_dl()
    except YleDlNotFound as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    url = questionary.text("Paste the Yle Areena video address:").ask()
    if not url or not url.strip():
        console.print("[yellow]No address entered.[/yellow]")
        return 1
    return url.strip()


def _download_yle(url: str) -> tuple[Path, Path] | int:
    """Download the URL. Returns (file, temp_dir) or an exit code."""
    temp_dir = Path(tempfile.mkdtemp(prefix="mib3_yle_"))
    console.print("[cyan]Downloading from Yle Areena…[/cyan]")
    try:
        src = download_from_yle(url.strip(), temp_dir)
    except DownloadError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        console.print(f"[red]{exc}[/red]")
        return 1
    console.print(f"[green]Downloaded:[/green] {src.name}")
    return src, temp_dir


def _run_conversion(
    args: argparse.Namespace,
    src: Path,
    auto: bool,
    out_dir: Path | None = None,
) -> int:
    """Probe src, decide the output path, and transcode. `auto` skips prompts."""
    profile = PROFILES[args.profile]
    if args.preset:
        profile = dataclasses.replace(profile, preset=args.preset)

    try:
        info = probe(src)
    except ConversionError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    _show_source(info, src)

    # --- resolve output --------------------------------------------------
    if args.output:
        dst = Path(args.output).expanduser()
    elif out_dir is not None:
        dst = out_dir / f"{safe_filename(src.stem)}_mib3.mp4"
    elif auto:
        # Downloaded original lives in a temp dir; drop the result in the CWD.
        dst = Path.cwd() / f"{safe_filename(src.stem)}_mib3.mp4"
    else:
        dst = _default_output(src)

    if dst.resolve() == src.resolve():
        console.print("[red]Output path is the same as the input. Aborting.[/red]")
        return 2
    if dst.exists() and not args.yes and not auto:
        import questionary

        overwrite = questionary.confirm(
            f"{dst.name} already exists. Overwrite?", default=False
        ).ask()
        if not overwrite:
            console.print("[yellow]Cancelled.[/yellow]")
            return 1
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        console.print(f"[red]Cannot create output folder {dst.parent}:[/red] {exc}")
        return 2
    if not os.access(dst.parent, os.W_OK):
        console.print(f"[red]Output folder is not writable:[/red] {dst.parent}")
        return 2
    # Prove the exact filename can be created here before spending minutes
    # encoding — catches illegal names, full disks and read-only mounts early.
    if not dst.exists():
        try:
            dst.touch()
            dst.unlink()
        except OSError as exc:
            console.print(f"[red]Cannot create output file:[/red] {dst}\n{exc}")
            console.print(
                "[yellow]Tip: FAT32/exFAT sticks reject : \" * ? < > | \\ in "
                "filenames. Use -o to choose a different name.[/yellow]"
            )
            return 2

    copy_v, copy_a = plan(profile, info)
    if copy_v and copy_a:
        how = "[green]remuxing (no re-encode — already MIB3-ready)[/green]"
    elif copy_v:
        how = f"copying video, re-encoding audio · [cyan]{profile.name}[/cyan]"
    elif copy_a:
        how = f"re-encoding video ([cyan]{profile.preset}[/cyan]), copying audio"
    else:
        how = f"re-encoding · [cyan]{profile.name}[/cyan] · preset [cyan]{profile.preset}[/cyan]"
    console.print(f"{how} → [green]{dst}[/green]")

    # --- convert with progress ------------------------------------------
    progress = Progress(
        TextColumn("[bold blue]Encoding"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    )
    try:
        with progress:
            task = progress.add_task("encode", total=1000)

            def on_progress(fraction: float) -> None:
                progress.update(task, completed=int(fraction * 1000))

            convert(src, dst, profile, info, on_progress=on_progress)
            progress.update(task, completed=1000)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled — partial output removed.[/yellow]")
        return 130
    except ConversionError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    size_mb = dst.stat().st_size / (1024 * 1024)
    console.print(
        Panel(
            f"[green]Done![/green]  {dst}\n{size_mb:.1f} MB — copy this to a "
            "FAT32/exFAT USB stick and plug it into the car.",
            border_style="green",
            expand=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
