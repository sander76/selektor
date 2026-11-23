from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Matched:
    match: re.Match[str]

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
            matches.append(
                Matched(
                    match=match,
                    start=start,
                    end=end,
                )
            )

    return sorted(matches, key=lambda matched: matched.match.start())
