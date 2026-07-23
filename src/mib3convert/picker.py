"""Full-screen, arrow-navigable terminal UI for choosing the video file.

An fzf-style picker built on Textual: a scrolling list you move through with
the arrow keys, plus a live search box that fuzzy-filters as you type. Enter
selects the highlighted file, Esc cancels.
"""

from __future__ import annotations

import os
from pathlib import Path

# Extensions we recognise as "video" when scanning a directory.
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
    """Subsequence fuzzy match. Returns a sort key (lower = better) or None.

    Ranks by tightest match span, then earliest first-match position, then
    shorter text — so exact/contiguous hits float to the top.
    """
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
    """One selectable row: display label + the real path."""

    __slots__ = ("path", "label", "haystack")

    def __init__(self, path: Path, root: Path):
        self.path = path
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        self.label = f"{rel}  [dim]({_human_size(path)})[/dim]"
        self.haystack = str(rel)


def _build_app(entries: list["_Entry"], root: Path):
    """Construct the Textual picker App (imported lazily so --help stays fast)."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.widgets import Footer, Input, Label, OptionList
    from textual.widgets.option_list import Option

    class VideoPicker(App):
        CSS = """
        Screen { layout: vertical; }
        #title { padding: 0 1; color: $accent; text-style: bold; }
        #search { margin: 0 1; }
        #count { padding: 0 1; color: $text-muted; }
        OptionList { height: 1fr; margin: 0 1; border: round $accent; }
        """
        BINDINGS = [
            Binding("escape", "cancel", "Cancel"),
            Binding("up", "cursor_up", "Up", show=True, priority=True),
            Binding("down", "cursor_down", "Down", show=True, priority=True),
            Binding("enter", "choose", "Select", priority=True),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.selected: Path | None = None
            self._matches: list[_Entry] = []

        def compose(self) -> ComposeResult:
            yield Label(f"Select a video to convert  —  {root}", id="title")
            yield Input(placeholder="Type to search… (↑/↓ to move, Enter to pick, Esc to cancel)", id="search")
            yield Label("", id="count")
            with Vertical():
                yield OptionList(id="results")
            yield Footer()

        def on_mount(self) -> None:
            self._refresh("")
            self.query_one("#search", Input).focus()

        def _refresh(self, query: str) -> None:
            scored = []
            for e in entries:
                s = fuzzy_score(query, e.haystack)
                if s is not None:
                    scored.append((s, e))
            scored.sort(key=lambda pair: pair[0])
            matches = [e for _, e in scored]

            ol = self.query_one("#results", OptionList)
            ol.clear_options()
            ol.add_options([Option(e.label, id=str(i)) for i, e in enumerate(matches)])
            self._matches = matches
            if matches:
                ol.highlighted = 0
            self.query_one("#count", Label).update(
                f"{len(matches)} of {len(entries)} file(s)"
            )

        def on_input_changed(self, event) -> None:
            self._refresh(event.value)

        def on_input_submitted(self, event) -> None:
            self.action_choose()

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

        def on_option_list_option_selected(self, event) -> None:
            # Mouse click / activation on a row.
            idx = event.option_index
            if 0 <= idx < len(self._matches):
                self.selected = self._matches[idx].path
                self.exit(self.selected)

        def action_choose(self) -> None:
            ol = self.query_one("#results", OptionList)
            idx = ol.highlighted
            if idx is not None and 0 <= idx < len(self._matches):
                self.selected = self._matches[idx].path
                self.exit(self.selected)

        def action_cancel(self) -> None:
            self.selected = None
            self.exit(None)

    return VideoPicker()


def pick_video(root: Path) -> Path | None:
    """Open the full-screen picker under root. Returns the chosen path or None."""
    videos = find_videos(root)
    if not videos:
        return _prompt_path(root)

    entries = [_Entry(p, root) for p in videos]
    app = _build_app(entries, root)
    return app.run()


def _prompt_path(root: Path) -> Path | None:
    """Fallback when no video files are found under root."""
    import questionary

    questionary.print(f"No video files found under {root}.", style="fg:#ffaf00")
    answer = questionary.path("Enter the path to the video file:").ask()
    if not answer:
        return None
    p = Path(answer).expanduser()
    if not p.is_file():
        questionary.print(f"Not a file: {p}", style="fg:#ff5f5f")
        return None
    return p
