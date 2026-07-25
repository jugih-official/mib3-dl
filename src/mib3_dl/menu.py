"""Small full-screen, arrow-navigable menu built on Textual."""

from __future__ import annotations


def _build_menu(title: str, options: list[tuple[str, str]]):
    """Construct the Textual menu App (imported lazily)."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.widgets import Footer, Label, OptionList
    from textual.widgets.option_list import Option

    values = [value for _, value in options]

    class Menu(App):
        CSS = """
        Screen { align: center middle; }
        #title { text-style: bold; color: $accent; padding: 1 2; }
        OptionList { width: 60; height: auto; border: round $accent; }
        """
        BINDINGS = [Binding("escape", "cancel", "Cancel")]

        def compose(self) -> ComposeResult:
            yield Label(title, id="title")
            yield OptionList(
                *[Option(label, id=str(i)) for i, (label, _) in enumerate(options)]
            )
            yield Footer()

        def on_mount(self) -> None:
            ol = self.query_one(OptionList)
            ol.highlighted = 0
            ol.focus()

        def on_option_list_option_selected(self, event) -> None:
            self.exit(values[event.option_index])

        def action_cancel(self) -> None:
            self.exit(None)

    return Menu()


def choose(title: str, options: list[tuple[str, str]]) -> str | None:
    """Show a full-screen menu. options is a list of (label, value).

    Returns the chosen value, or None if the user pressed Esc.
    """
    return _build_menu(title, options).run()
