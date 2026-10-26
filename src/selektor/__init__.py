from __future__ import annotations

import argparse
import bisect
import curses
import re
import sys
from pathlib import Path


def _match_ranges(
    matches: list[re.Match[str]], lines: list[str], line_starts: list[int]
) -> list[list[tuple[int, int, int]]]:
    ranges: list[list[tuple[int, int, int]]] = [[] for _ in lines]

    for match_index, match in enumerate(matches):
        start, end = match.span()
        if start == end:
            line_index = min(bisect.bisect_right(line_starts, start) - 1, len(lines) - 1)
            line_start = line_starts[line_index]
            line_length = len(lines[line_index])
            char_index = start - line_start
            if char_index == line_length and char_index:
                char_index -= 1
            if char_index < line_length:
                ranges[line_index].append((char_index, char_index + 1, match_index))
            continue

        first_line = bisect.bisect_right(line_starts, start) - 1
        last_line = bisect.bisect_right(line_starts, end - 1) - 1
        for line_index in range(first_line, last_line + 1):
            line_start = line_starts[line_index]
            visible_start = max(start, line_start) - line_start
            visible_end = min(end, line_start + len(lines[line_index])) - line_start
            if visible_start < visible_end:
                ranges[line_index].append((visible_start, visible_end, match_index))

    return ranges


def _browse(
    matches: list[re.Match[str]], lines: list[str], line_starts: list[int]
) -> str | None:
    ranges = _match_ranges(matches, lines, line_starts)
    selected = 0
    focus_line = (
        min(bisect.bisect_right(line_starts, matches[0].start()) - 1, len(lines) - 1)
        if matches
        else 0
    )

    def draw(screen: curses.window) -> None:
        rows, columns = screen.getmaxyx()
        content_rows = max(rows - 2, 1)
        usable_columns = max(columns - 1, 0)
        top = max(0, min(focus_line - content_rows // 2, len(lines) - content_rows))
        screen.erase()

        for screen_row in range(min(content_rows, len(lines) - top)):
            line_index = top + screen_row
            line = lines[line_index]
            intervals = ranges[line_index]
            boundaries = {0, min(len(line), usable_columns)}
            for start, end, _ in intervals:
                if start < usable_columns:
                    boundaries.add(start)
                    boundaries.add(min(end, usable_columns))
            points = sorted(boundaries)

            for start, end in zip(points, points[1:]):
                if start >= end:
                    continue
                active = [
                    match_index
                    for match_start, match_end, match_index in intervals
                    if match_start < end and match_end > start
                ]
                if selected in active:
                    attribute = curses.A_REVERSE | curses.A_BOLD
                elif active:
                    attribute = curses.A_UNDERLINE
                else:
                    attribute = curses.A_NORMAL
                try:
                    screen.addstr(screen_row, start, line[start:end], attribute)
                except curses.error:
                    pass

        if matches:
            footer = (
                f"Match {selected + 1}/{len(matches)}  "
                "n: next  Enter: select  q: quit"
            )
        else:
            footer = "No matches found. Press Enter or q to quit."
        try:
            screen.addnstr(rows - 1, 0, footer, usable_columns, curses.A_DIM)
        except curses.error:
            pass
        screen.refresh()

    def run(screen: curses.window) -> str | None:
        nonlocal selected, focus_line
        try:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Browse a file's regex matches in the terminal."
    )
    parser.add_argument("file", type=Path, help="file to search")
    parser.add_argument("regex", help="regular expression to match")
    args = parser.parse_args(argv)

    try:
        text = args.file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        parser.error(f"cannot read {args.file}: {error}")

    try:
        matches = list(re.finditer(args.regex, text))
    except re.error as error:
        parser.error(f"invalid regular expression: {error}")

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("interactive selection requires a terminal")

    lines = text.split("\n")
    line_starts = [0]
    line_starts.extend(index + 1 for index, char in enumerate(text) if char == "\n")
    selected_text = _browse(matches, lines, line_starts)
    if selected_text is None:
        return 1
    print(selected_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
