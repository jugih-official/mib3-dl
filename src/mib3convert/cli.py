"""Command-line entry point for mib3convert."""

from __future__ import annotations

import argparse
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
    probe,
)
from .downloader import (
    DownloadError,
    YleDlNotFound,
    download_from_yle,
    ensure_yle_dl,
)
from .menu import choose
from .picker import pick_video
from .profiles import DEFAULT_PROFILE, PROFILES

console = Console()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mib3convert",
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
    p.add_argument("--version", action="version", version=f"mib3convert {__version__}")
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


def _default_output(src: Path) -> Path:
    return src.with_name(f"{src.stem}_mib3.mp4")


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
                rc = _resolve_yle()
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

        return _run_conversion(args, src, auto)
    except KeyboardInterrupt:
        console.print("[yellow]Cancelled.[/yellow]")
        return 130
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)

def _resolve_yle() -> tuple[Path, Path] | int:
    """Prompt for a Yle Areena URL and download it.

    Returns (downloaded_file, temp_dir) on success, or an exit code on failure.
    """
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


def _run_conversion(args: argparse.Namespace, src: Path, auto: bool) -> int:
    """Probe src, decide the output path, and transcode. `auto` skips prompts."""
    profile = PROFILES[args.profile]

    try:
        info = probe(src)
    except ConversionError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    _show_source(info, src)

    # --- resolve output --------------------------------------------------
    if args.output:
        dst = Path(args.output).expanduser()
    elif auto:
        # Downloaded original lives in a temp dir; drop the result in the CWD.
        dst = Path.cwd() / f"{src.stem}_mib3.mp4"
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
    dst.parent.mkdir(parents=True, exist_ok=True)

    console.print(
        f"Converting with [cyan]{profile.name}[/cyan] profile → [green]{dst}[/green]"
    )

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
