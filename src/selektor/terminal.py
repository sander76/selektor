from __future__ import annotations

import curses
import os
import sys
from dataclasses import dataclass, field
from itertools import pairwise

from .matchers import open_in_pycharm, open_in_vim
from .matching import Matched, find_matches

ORANGE_COLOR = 20
MATCH_HIGHLIGHT_PAIR = 1
SELECTED_MATCH_PAIR = 2
WINDOW_BACKGROUND_PAIR = 3
WINDOW_BACKGROUND_COLOR = 16
WINDOW_BACKGROUND_FALLBACK = 234


class Color:
    _as_tuple: None | tuple[int, int, int] = None

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
class Line:
    text: str
    matches: list[Matched] = field(default_factory=list)

    def render(
        self,
        screen: curses.window,
        screen_row: int,
        usable_columns: int,
        has_color: bool,
    ) -> None:
        # Split the line at match edges so each rendered segment has one style.
        boundaries = {0, min(len(self.text), usable_columns)}
        for match in self.matches:
            if match.start < usable_columns:
                boundaries.add(match.start)
                boundaries.add(min(match.end, usable_columns))
        points = sorted(boundaries)

        for start, end in pairwise(points):
            if start >= end:
                continue
            active_matches = [
                match
                for match in self.matches
                if match.start < end and match.end > start
            ]
            if any(match.selected for match in active_matches):
                attribute = (
                    curses.color_pair(SELECTED_MATCH_PAIR) | curses.A_UNDERLINE
                    if has_color
                    else curses.A_UNDERLINE
                )
            elif active_matches:
                attribute = (
                    curses.color_pair(MATCH_HIGHLIGHT_PAIR) | curses.A_BOLD
                    if has_color
                    else curses.A_UNDERLINE
                )
            else:
                attribute = curses.A_NORMAL
            try:
                screen.addstr(screen_row, start, self.text[start:end], attribute)
            except curses.error:
                pass


class LineCollection:
    def __init__(self, text: str, matches: list[Matched]) -> None:
        self.lines = tuple(Line(line) for line in text.split("\n"))
        self.matches = matches
        for match in self.matches:
            self.lines[match.line_index].matches.append(match)

        self._selected_index: int | None = None
        if self.matches:
            self._selected_index = len(self.matches) - 1
            self.matches[self._selected_index].selected = True

    @property
    def selected_line_index(self) -> int:
        if self._selected_index is None:
            return 0
        return self.matches[self._selected_index].line_index

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
    first_draw = True

    def draw(screen: curses.window) -> None:
        nonlocal first_draw
        # Reserve the last row for the footer and the last column to avoid wrapping.
        rows, columns = screen.getmaxyx()
        content_rows = max(rows - 2, 1)
        usable_columns = max(columns - 1, 0)

        has_color = curses.has_colors()
        if first_draw:
            top = max(0, len(line_collection.lines) - content_rows)
        else:
            # Keep the line containing the focused match near the vertical center.
            top = max(
                0,
                min(
                    line_collection.selected_line_index - content_rows // 2,
                    len(line_collection.lines) - content_rows,
                ),
            )

        screen.erase()

        for screen_row in range(min(content_rows, len(line_collection.lines) - top)):
            # Translate the visible row into its corresponding input line.
            line_index = top + screen_row
            line_collection.lines[line_index].render(
                screen, screen_row, usable_columns, has_color
            )

        first_draw = False
        selected_text = line_collection.selected_text
        if selected_text is not None:
            footer = (
                f"Match {line_collection.selected_number}/"
                f"{len(line_collection.matches)}: {selected_text}  "
                "n: next  N: previous  ov: vim  Enter: select  q: quit"
            )
        else:
            footer = "No matches found. Press Enter or q to quit."
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
        pending_open = False
        while True:
            draw(screen)
            key = screen.getch()

            if pending_open:
                assert (
                    line_collection.selected_text is not None
                )  # make type checker happy
                if key == ord("v"):
                    return open_in_vim(line_collection.selected_text)
                if key == ord("p"):
                    return open_in_pycharm(line_collection.selected_text)

            pending_open = False
            if key in (ord("q"), 27):
                return None
            if not line_collection.matches:
                if key in (curses.KEY_ENTER, 10, 13):
                    return None
                continue
            if key == ord("n"):
                line_collection.select_next()
            elif key == ord("N"):
                line_collection.select_previous()
            elif key == ord("o"):
                if line_collection.selected_text is not None:
                    pending_open = True
            elif key in (curses.KEY_ENTER, 10, 13):
                return line_collection.selected_text

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
