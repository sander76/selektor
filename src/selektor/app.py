from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .terminal import browse


def find_matches(patterns: list[str], text: str) -> list[re.Match[str]]:
    matches = [
        match
        for pattern in patterns
        for match in re.finditer(pattern, text)
        if match.start() < match.end()
    ]
    return sorted(matches, key=lambda match: match.start())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Browse regex matches in a file or stdin. Provide a file or '-' "
            "followed by one or more regexes."
        )
    )
    parser.add_argument(
        "source",
        metavar="FILE",
        help="file to read, or '-' to read from stdin",
    )
    parser.add_argument(
        "patterns",
        nargs="+",
        metavar="REGEX",
        help="one or more regular expressions to find",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    patterns = args.patterns

    if args.source == "-":
        try:
            text = sys.stdin.read()
        except UnicodeError as error:
            parser.error(f"cannot decode stdin as UTF-8: {error}")
    else:
        file = Path(args.source)
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            parser.error(f"cannot read {file}: {error}")

    try:
        matches = find_matches(patterns, text)
    except re.error as error:
        parser.error(f"invalid regular expression: {error}")

    lines = text.split("\n")
    line_starts = [0]
    line_starts.extend(index + 1 for index, char in enumerate(text) if char == "\n")

    try:
        selected_text = browse(matches, lines, line_starts)
    except RuntimeError as error:
        parser.error(str(error))

    if selected_text is None:
        return 1

    print(selected_text)
    return 0
