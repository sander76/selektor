from __future__ import annotations

import bisect
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MatchRange:
    start: int
    end: int
    match_index: int


def find_matches(patterns: list[str], text: str) -> list[re.Match[str]]:
    matches = [
        match
        for pattern in patterns
        for match in re.finditer(pattern, text)
        if match.start() < match.end()
    ]
    return sorted(matches, key=lambda match: match.start())


def match_ranges(
    matches: list[re.Match[str]], lines: list[str], line_starts: list[int]
) -> list[list[MatchRange]]:
    """Map match spans to per-line character ranges for terminal highlighting."""
    ranges: list[list[MatchRange]] = [[] for _ in lines]

    for match_index, match in enumerate(matches):
        start, end = match.span()
        # Spans are half-open; end - 1 finds the last line containing a match.
        first_line = bisect.bisect_right(line_starts, start) - 1
        last_line = bisect.bisect_right(line_starts, end - 1) - 1
        for line_index in range(first_line, last_line + 1):
            line_start = line_starts[line_index]
            # Clip to visible characters and use line-relative offsets.
            visible_start = max(start, line_start) - line_start
            visible_end = min(end, line_start + len(lines[line_index])) - line_start
            if visible_start < visible_end:
                # Preserve identity so the renderer can style the selected match.
                ranges[line_index].append(
                    MatchRange(visible_start, visible_end, match_index)
                )

    return ranges
