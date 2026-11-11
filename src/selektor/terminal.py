from __future__ import annotations

import bisect
import curses
import os
import re
import sys
from dataclasses import dataclass

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
    curses.init_pair(WINDOW_BACKGROUND_PAIR, curses.COLOR_WHITE, WINDOW_BACKGROUND_COLOR)


@dataclass(frozen=True)
class MatchRange:
    start: int
    end: int
    match_index: int


def match_ranges(
    matches: list[re.Match[str]], lines: list[str], line_starts: list[int]
) -> list[list[MatchRange]]:
    """Map match spans to per-line character ranges for terminal highlighting."""
    ranges: list[list[MatchRange]] = [[] for _ in lines]

    for match_index, match in enumerate(matches):
        start, end = match.span()
        first_line = bisect.bisect_right(line_starts, start) - 1
        last_line = bisect.bisect_right(line_starts, end - 1) - 1
        for line_index in range(first_line, last_line + 1):
            line_start = line_starts[line_index]
            visible_start = max(start, line_start) - line_start
            visible_end = min(end, line_start + len(lines[line_index])) - line_start
            if visible_start < visible_end:
                ranges[line_index].append(
                    MatchRange(visible_start, visible_end, match_index)
                )

    return ranges


def browse_on_terminal(matches: list[re.Match[str]], lines: list[str], line_starts: list[int]) -> str | None:
    ranges = match_ranges(matches, lines, line_starts)
    selected = 0
    focus_line = min(bisect.bisect_right(line_starts, matches[0].start()) - 1, len(lines) - 1) if matches else 0

    def draw(screen: curses.window) -> None:
        rows, columns = screen.getmaxyx()
        content_rows = max(rows - 2, 1)
        usable_columns = max(columns - 1, 0)
        has_color = curses.has_colors()
        top = max(0, min(focus_line - content_rows // 2, len(lines) - content_rows))
        screen.erase()

        for screen_row in range(min(content_rows, len(lines) - top)):
            line_index = top + screen_row
            line = lines[line_index]
            intervals = ranges[line_index]
            boundaries = {0, min(len(line), usable_columns)}
            for match_range in intervals:
                if match_range.start < usable_columns:
                    boundaries.add(match_range.start)
                    boundaries.add(min(match_range.end, usable_columns))
            points = sorted(boundaries)

            for start, end in zip(points, points[1:]):
                if start >= end:
                    continue
                active = [
                    match_range.match_index
                    for match_range in intervals
                    if match_range.start < end and match_range.end > start
                ]
                if selected in active:
                    attribute = (
                        curses.color_pair(SELECTED_MATCH_PAIR) | curses.A_UNDERLINE if has_color else curses.A_UNDERLINE
                    )
                elif active:
                    attribute = (
                        curses.color_pair(MATCH_HIGHLIGHT_PAIR) | curses.A_BOLD if has_color else curses.A_UNDERLINE
                    )
                else:
                    attribute = curses.A_NORMAL
                try:
                    screen.addstr(screen_row, start, line[start:end], attribute)
                except curses.error:
                    pass

        if matches:
            footer = f"Match {selected + 1}/{len(matches)}  n: next  Enter: select  q: quit"
        else:
            footer = "No matches found. Press Enter or q to quit."
        try:
            screen.addnstr(rows - 1, 0, footer, usable_columns, curses.A_DIM)
        except curses.error:
            pass
        screen.refresh()

    def run(screen: curses.window) -> str | None:
        nonlocal selected, focus_line
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
            if key in (ord("q"), 27):
                return None
            if not matches:
                if key in (curses.KEY_ENTER, 10, 13):
                    return None
                continue
            if key == ord("n"):
                selected = (selected + 1) % len(matches)
                focus_line = min(
                    bisect.bisect_right(line_starts, matches[selected].start()) - 1,
                    len(lines) - 1,
                )
            elif key in (curses.KEY_ENTER, 10, 13):
                return matches[selected].group(0)

    return curses.wrapper(run)


def browse(matches: list[re.Match[str]], lines: list[str], line_starts: list[int]) -> str | None:
    if sys.stdin.isatty() and sys.stdout.isatty():
        return browse_on_terminal(matches, lines, line_starts)

    try:
        terminal_fd = os.open("/dev/tty", os.O_RDWR)
    except OSError as error:
        raise RuntimeError("interactive selection requires a terminal") from error

    saved_stdin = os.dup(0)
    saved_stdout = os.dup(1)
    try:
        os.dup2(terminal_fd, 0)
        os.dup2(terminal_fd, 1)
        return browse_on_terminal(matches, lines, line_starts)
    finally:
        os.dup2(saved_stdin, 0)
        os.dup2(saved_stdout, 1)
        os.close(saved_stdin)
        os.close(saved_stdout)
        os.close(terminal_fd)
