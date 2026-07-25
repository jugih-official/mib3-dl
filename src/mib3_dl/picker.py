"""Full-screen, arrow-navigable filesystem browser for choosing a video.

A Textual TUI that browses the filesystem from any starting directory: move
with the arrow keys, Enter opens a folder or picks a file, `..` goes up, and you
can type a path (e.g. ``/media/usb`` or ``~/Videos``) to jump anywhere. A live
box fuzzy-filters the current folder as you type. Esc cancels.
"""

from __future__ import annotations

import os
from pathlib import Path

# Extensions we recognise as "video".
VIDEO_EXTS = {
    ".mkv", ".avi", ".mp4", ".m4v", ".mov", ".wmv", ".flv", ".webm",
    ".mpg", ".mpeg", ".m2ts", ".mts", ".ts", ".vob", ".3gp", ".ogv",
    ".divx", ".asf", ".rm", ".rmvb", ".f4v",
}


def find_videos(root: Path, max_results: int = 5000) -> list[Path]:
    """Recursively collect video files under root, skipping hidden dirs."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if Path(name).suffix.lower() in VIDEO_EXTS:
                found.append(Path(dirpath) / name)
                if len(found) >= max_results:
                    return found
    return found


def _human_size(path: Path) -> str:
    try:
        size = float(path.stat().st_size)
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def fuzzy_score(query: str, text: str) -> tuple | None:
    """Subsequence fuzzy match. Returns a sort key (lower = better) or None."""
    if not query:
        return (0, 0, len(text))
    q = query.lower()
    t = text.lower()
    pos = -1
    first = None
    for ch in q:
        pos = t.find(ch, pos + 1)
        if pos == -1:
            return None
        if first is None:
            first = pos
    span = pos - (first or 0)
    return (span, first or 0, len(text))


class _Entry:
    """One row: 'use this folder', a parent link, a directory, or a video file."""

    __slots__ = ("kind", "path", "name", "label")

    def __init__(self, kind: str, path: Path, name: str):
        self.kind = kind  # "use" | "up" | "dir" | "file"
        self.path = path
        self.name = name
        if kind == "use":
            self.label = "[green bold]✓ Use this folder[/green bold]"
        elif kind == "up":
            self.label = "[cyan]../[/cyan]  [dim](parent folder)[/dim]"
        elif kind == "dir":
            self.label = f"[cyan]{name}/[/cyan]"
        else:
            self.label = f"{name}  [dim]({_human_size(path)})[/dim]"


def _list_dir(directory: Path, dirs_only: bool = False) -> list[_Entry]:
    """Entries for a directory.

    File mode: parent link, subfolders, then video files.
    Folder mode (dirs_only): a 'use this folder' row, parent link, subfolders.
    """
    entries: list[_Entry] = []
    if dirs_only:
        entries.append(_Entry("use", directory, "."))
    if directory.parent != directory:  # not the filesystem root
        entries.append(_Entry("up", directory.parent, ".."))
    try:
        children = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except (PermissionError, OSError):
        return entries

    dirs, files = [], []
    for child in children:
        if child.name.startswith("."):
            continue
        try:
            if child.is_dir():
                dirs.append(_Entry("dir", child, child.name))
            elif not dirs_only and child.is_file() and child.suffix.lower() in VIDEO_EXTS:
                files.append(_Entry("file", child, child.name))
        except OSError:
            continue
    entries.extend(dirs)
    entries.extend(files)
    return entries


def _build_app(start_dir: Path, dirs_only: bool = False, heading: str = ""):
    """Construct the Textual browser App (imported lazily).

    dirs_only=True turns it into an output-folder chooser.
    """
    from rich.text import Text
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.widgets import Footer, Input, Label, OptionList
    from textual.widgets.option_list import Option

    class VideoBrowser(App):
        CSS = """
        Screen { layout: vertical; }
        #heading { padding: 0 1; color: $success; text-style: bold; }
        #cwd { padding: 0 1; color: $accent; text-style: bold; }
        #search { margin: 0 1; }
        #count { padding: 0 1; color: $text-muted; }
        OptionList { height: 1fr; margin: 0 1; border: round $accent; }
        """
        BINDINGS = [
            Binding("escape", "cancel", "Cancel"),
            Binding("up", "cursor_up", "Up", priority=True),
            Binding("down", "cursor_down", "Down", priority=True),
            Binding("ctrl+u", "go_up", "Parent", priority=True),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.selected: Path | None = None
            self._cwd = start_dir
            self._entries: list[_Entry] = []
            self._matches: list[_Entry] = []

        def compose(self) -> ComposeResult:
            if heading:
                yield Label(heading, id="heading")
            yield Label("", id="cwd")
            yield Input(
                placeholder="Type to filter · /path or ~ to jump · ↑↓ move · Enter open/pick · Esc cancel",
                id="search",
            )
            yield Label("", id="count")
            with Vertical():
                yield OptionList(id="results")
            yield Footer()

        def on_mount(self) -> None:
            self._load_dir(self._cwd)
            self.query_one("#search", Input).focus()

        # --- data ------------------------------------------------------
        def _load_dir(self, directory: Path) -> None:
            self._cwd = directory.resolve()
            self._entries = _list_dir(self._cwd, dirs_only=dirs_only)
            self.query_one("#cwd", Label).update(f"📁 {self._cwd}")
            search = self.query_one("#search", Input)
            if search.value:
                search.value = ""  # triggers on_input_changed → _refresh("")
            else:
                self._refresh("")

        def _refresh(self, query: str) -> None:
            if not query:
                # Natural order: parent link, then folders, then files.
                matches = list(self._entries)
            else:
                # While searching, drop the parent link and rank by fuzzy score.
                scored = []
                for e in self._entries:
                    if e.kind in ("up", "use"):
                        continue
                    s = fuzzy_score(query, e.name)
                    if s is not None:
                        scored.append((s, e))
                scored.sort(key=lambda pair: pair[0])
                matches = [e for _, e in scored]

            ol = self.query_one("#results", OptionList)
            ol.clear_options()
            ol.add_options(
                [Option(Text.from_markup(e.label), id=str(i)) for i, e in enumerate(matches)]
            )
            self._matches = matches
            if matches:
                ol.highlighted = 0
            ndirs = sum(1 for e in self._entries if e.kind == "dir")
            if dirs_only:
                summary = f"{ndirs} subfolder(s)"
            else:
                nfiles = sum(1 for e in self._entries if e.kind == "file")
                summary = f"{ndirs} folder(s), {nfiles} video(s)"
            self.query_one("#count", Label).update(summary)

        # --- events ----------------------------------------------------
        def on_input_changed(self, event) -> None:
            self._refresh(event.value)

        def on_input_submitted(self, event) -> None:
            text = event.value.strip()
            # Typed path → jump straight there.
            if text and (text.startswith("/") or text.startswith("~") or text.startswith(".")):
                target = Path(text).expanduser()
                if target.is_dir():
                    self._load_dir(target)
                    return
                if target.is_file() and target.suffix.lower() in VIDEO_EXTS:
                    self._choose(target)
                    return
            self._activate_highlighted()

        def on_option_list_option_selected(self, event) -> None:
            idx = event.option_index
            if 0 <= idx < len(self._matches):
                self._activate(self._matches[idx])

        # --- actions ---------------------------------------------------
        def _activate_highlighted(self) -> None:
            ol = self.query_one("#results", OptionList)
            idx = ol.highlighted
            if idx is not None and 0 <= idx < len(self._matches):
                self._activate(self._matches[idx])

        def _activate(self, entry: _Entry) -> None:
            if entry.kind == "use":
                self._choose(self._cwd)
            elif entry.kind in ("up", "dir"):
                self._load_dir(entry.path)
            else:
                self._choose(entry.path)

        def _choose(self, path: Path) -> None:
            self.selected = path
            self.exit(path)

        def action_go_up(self) -> None:
            if self._cwd.parent != self._cwd:
                self._load_dir(self._cwd.parent)

        def action_cursor_down(self) -> None:
            ol = self.query_one("#results", OptionList)
            if ol.option_count:
                cur = ol.highlighted if ol.highlighted is not None else -1
                ol.highlighted = min(cur + 1, ol.option_count - 1)

        def action_cursor_up(self) -> None:
            ol = self.query_one("#results", OptionList)
            if ol.option_count:
                cur = ol.highlighted if ol.highlighted is not None else 0
                ol.highlighted = max(cur - 1, 0)

        def action_cancel(self) -> None:
            self.selected = None
            self.exit(None)

    return VideoBrowser()


def pick_video(root: Path) -> Path | None:
    """Open the filesystem browser starting at root. Returns the chosen path."""
    start = root if root.is_dir() else Path.cwd()
    return _build_app(start, heading="Select a video to convert").run()


def pick_directory(root: Path, heading: str = "Select the output folder") -> Path | None:
    """Open the folder chooser starting at root. Returns the chosen directory."""
    start = root if root.is_dir() else Path.cwd()
    return _build_app(start, dirs_only=True, heading=heading).run()
