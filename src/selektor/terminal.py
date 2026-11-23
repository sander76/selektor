from __future__ import annotations

import curses
import os
import sys
from collections.abc import Generator
from dataclasses import dataclass, field

from .matchers import open_in_pycharm, open_in_vim
from .matching import Matched, find_matches

ORANGE_COLOR = 20
MATCH_HIGHLIGHT_PAIR = 1
SELECTED_MATCH_PAIR = 2
WINDOW_BACKGROUND_PAIR = 3
WINDOW_BACKGROUND_COLOR = 16
WINDOW_BACKGROUND_FALLBACK = 234


class Color:
    _as_tuple: tuple[int, int, int] | None = None

    def __init__(self, red: int, green: int, blue: int):
        self._red = red
        self._green = green
        self._blue = blue

    def _to_curses_color(self, color: int):
        return round((color * 1000) / 255)

    def as_tuple(self) -> tuple[int, int, int]:
        if self._as_tuple is None:
            self._as_tuple = (
                self._to_curses_color(self._red),
                self._to_curses_color(self._green),
                self._to_curses_color(self._blue),
            )
        return self._as_tuple


PANELBACKGROUND = Color(20, 33, 61)
MATCH_COLOR = Color(252, 163, 17)


@dataclass
class State:
    """State object.

    Defines the state of the tui like relevant keybindings and header info.
    """

    line_collection: LineCollection
    _state_manager: StateManager | None = field(default=None, init=False)

    @property
    def state_manager(self) -> StateManager:
        if self._state_manager is not None:
            return self._state_manager
        raise AttributeError("state manager is None")

    def footer(self) -> str: ...

    def watch_key(self, key: int) -> Result | None: ...

    def add_parent(self, parent: StateManager):
        self._state_manager = parent


@dataclass
class StateManager:
    opening_state: State
    normal_state: State
    current_state: State = field(init=False)

    def __post_init__(self):
        self.opening_state.add_parent(self)
        self.normal_state.add_parent(self)
        self.current_state = self.normal_state

    def set_state(self, state: State) -> None:
        self.current_state = state


@dataclass
class Result:
    value: str | None


@dataclass
class NormalState(State):
    def footer(self) -> str:
        if self.line_collection.selected_text is not None:
            footer = (
                f"Match {self.line_collection.selected_number}/"
                f"{len(self.line_collection.matches)}: {self.line_collection.selected_text}  "
                "n: next  N: previous  o: open...  Enter: select  q: quit"
            )
        else:
            footer = "No matches found. Press Enter or q to quit."
        return footer

    def watch_key(self, key: int) -> Result | None:
        if key in (ord("q"), 27):
            return Result(None)
        if key in (curses.KEY_ENTER, 10, 13):
            if not self.line_collection.matches:
                return Result(None)

            return Result(self.line_collection.selected_text)
        if key == ord("n"):
            self.line_collection.select_next()
        elif key == ord("N"):
            self.line_collection.select_previous()
        elif key == ord("o") and self.line_collection.selected_text is not None:
            self.state_manager.set_state(self.state_manager.opening_state)


@dataclass
class OpeningState(State):
    def footer(self) -> str:
        return "v: open in vim  p: open in pycharm  b: exit open mode"

    def watch_key(self, key: int) -> Result | None:
        assert self.line_collection.selected_text is not None  # make type checker happy
        if key == ord("v"):
            return Result(open_in_vim(self.line_collection.selected_text))
        if key == ord("p"):
            return Result(open_in_pycharm(self.line_collection.selected_text))
        if key in (ord("b"), 27):
            self.state_manager.set_state(self.state_manager.normal_state)


def ensure_color_terminal() -> None:
    term = os.environ.get("TERM", "").lower()
    if not term or term == "dumb":
        os.environ["TERM"] = "xterm-256color"


def configure_curses_colors() -> None:
    if not curses.has_colors():
        return
    curses.start_color()

    curses.init_color(WINDOW_BACKGROUND_COLOR, *PANELBACKGROUND.as_tuple())
    curses.init_color(ORANGE_COLOR, *MATCH_COLOR.as_tuple())

    curses.init_pair(MATCH_HIGHLIGHT_PAIR, ORANGE_COLOR, WINDOW_BACKGROUND_COLOR)
    curses.init_pair(SELECTED_MATCH_PAIR, ORANGE_COLOR, WINDOW_BACKGROUND_COLOR)
    curses.init_pair(
        WINDOW_BACKGROUND_PAIR, curses.COLOR_WHITE, WINDOW_BACKGROUND_COLOR
    )


@dataclass
class CharRenderer:
    """Renders a single character."""

    char: str
    matches: list[Matched] = field(default_factory=list, init=False)

    def render(self):
        attribute = curses.A_NORMAL
        if self.matches:
            attribute = curses.color_pair(MATCH_HIGHLIGHT_PAIR)
        if any(match.selected for match in self.matches):
            attribute = curses.color_pair(SELECTED_MATCH_PAIR) | curses.A_UNDERLINE
        return attribute


class LineCollection:
    def __init__(self, text: str, matches: list[Matched]) -> None:
        self.chars = {idx: CharRenderer(char=char) for idx, char in enumerate(text)}
        for match in matches:
            for idx in range(match.start, match.end):
                self.chars[idx].matches.append(match)

        self.matches = matches
        if self.matches:
            # select the last item by default at startup.
            self._selected_index = len(self.matches) - 1
            self.matches[self._selected_index].selected = True
        else:
            self._selected_index = None

    def _get_xy(self, screen_width) -> Generator[tuple[int, int, CharRenderer]]:
        row: int = 0
        col: int = 0
        for char in self.chars.values():
            if char.char == "\n" or col == screen_width:
                row += 1
                col = 0
            yield row, col, char
            col += 1

    def render(self, screen: curses.window, screen_height: int, screen_width: int):
        screen.clear()
        all_chars = (*self._get_xy(screen_width),)
        content_height = all_chars[-1][0]  # in rows

        # we always draw the content from the bottom to the top.
        # if the content height  < screen_height, the top rows are empty
        # if content height > screen_height, the first rows are cut off.
        screen_y = 0
        content_y = 0
        if content_height > screen_height:
            content_y = content_height - screen_height
        if content_height < screen_height:
            screen_y = screen_height - content_height

        for xychar in all_chars:
            y, x, char_renderer = xychar
            if y < content_y:
                continue
            screen.addstr(
                y - content_y + screen_y,
                x,
                char_renderer.char,
                char_renderer.render(),
            )

    @property
    def selected_number(self) -> int:
        if self._selected_index is None:
            return 0
        return self._selected_index + 1

    @property
    def selected_text(self) -> str | None:
        if self._selected_index is None:
            return None
        return self.matches[self._selected_index].match.group(0)

    def select_next(self) -> None:
        self._select_by(1)

    def select_previous(self) -> None:
        self._select_by(-1)

    def _select_by(self, offset: int) -> None:
        if self._selected_index is None:
            return
        self.matches[self._selected_index].selected = False

        # round trip selection. once outer limit index is selected, it all starts over.
        self._selected_index = (self._selected_index + offset) % len(self.matches)
        self.matches[self._selected_index].selected = True


def browse_on_terminal(line_collection: LineCollection) -> str | None:
    state_manager = StateManager(
        opening_state=OpeningState(line_collection=line_collection),
        normal_state=NormalState(line_collection=line_collection),
    )

    def draw(screen: curses.window) -> None:
        # Reserve the last row for the footer and the last column to avoid wrapping.
        rows, columns = screen.getmaxyx()
        content_rows = max(rows - 2, 1)
        usable_columns = max(columns - 1, 0)

        line_collection.render(
            screen, screen_width=usable_columns, screen_height=content_rows
        )

        footer = state_manager.current_state.footer()
        try:
            screen.addnstr(rows - 1, 0, footer, usable_columns, curses.A_DIM)
        except curses.error:
            pass
        screen.refresh()

    def run(screen: curses.window) -> str | None:
        ensure_color_terminal()
        try:
            configure_curses_colors()
            if curses.has_colors():
                screen.bkgd(" ", curses.color_pair(WINDOW_BACKGROUND_PAIR))
            curses.curs_set(0)
        except curses.error:
            pass
        screen.keypad(True)

        while True:
            draw(screen)
            key = screen.getch()

            result = state_manager.current_state.watch_key(key)
            if isinstance(result, Result):
                return result.value

    return curses.wrapper(run)


def browse(text: str, patterns: list[str]) -> str | None:
    matches = find_matches(patterns, text)
    line_collection = LineCollection(text, matches)

    if sys.stdin.isatty() and sys.stdout.isatty():
        return browse_on_terminal(line_collection)

    try:
        terminal_fd = os.open("/dev/tty", os.O_RDWR)
    except OSError as error:
        raise RuntimeError("interactive selection requires a terminal") from error

    saved_stdin = os.dup(0)
    saved_stdout = os.dup(1)
    try:
        os.dup2(terminal_fd, 0)
        os.dup2(terminal_fd, 1)
        return browse_on_terminal(line_collection)
    finally:
        os.dup2(saved_stdin, 0)
        os.dup2(saved_stdout, 1)
        os.close(saved_stdin)
        os.close(saved_stdout)
        os.close(terminal_fd)
