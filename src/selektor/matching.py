from __future__ import annotations

import bisect
import re
from dataclasses import dataclass


@dataclass
class Matched:
    match: re.Match[str]

    line_index: int
    """The line nr of the text where the match is found."""

    start: int
    """match start idx."""

    end: int
    """match stop idx."""

    selected: bool = False


def find_matches(patterns: list[str], text: str) -> list[Matched]:
    line_starts = [0]
    line_starts.extend(index + 1 for index, char in enumerate(text) if char == "\n")
    matches = []

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            start, end = match.span()
            if start == end:
                continue
            line_index = bisect.bisect_right(line_starts, start) - 1
            line_start = line_starts[line_index]
            matches.append(
                Matched(
                    match=match,
                    line_index=line_index,
                    start=start - line_start,
                    end=end - line_start,
                )
            )

    return sorted(matches, key=lambda matched: matched.match.start())
