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
    matches = [match for pattern in patterns for match in re.finditer(pattern, text) if match.start() < match.end()]
    return sorted(matches, key=lambda match: match.start())


def match_ranges(matches: list[re.Match[str]], lines: list[str], line_starts: list[int]) -> list[list[MatchRange]]:
    """Map single-line match spans to line-relative ranges for terminal highlighting."""
    ranges: list[list[MatchRange]] = [[] for _ in lines]

    for match_index, match in enumerate(matches):
        start, end = match.span()
        # A match stays on one line, so its start determines its line.
        line_index = bisect.bisect_right(line_starts, start) - 1
        line_start = line_starts[line_index]
        ranges[line_index].append(MatchRange(start - line_start, end - line_start, match_index))

    return ranges
