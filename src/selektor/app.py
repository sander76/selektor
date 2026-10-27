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
    ]
    return sorted(matches, key=lambda match: match.start())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Browse regex matches in a file or piped input. "
            "When FILE is omitted, read text from stdin. Multiple regexes may be "
            "provided."
        )
    )
    parser.add_argument(
        "source_and_patterns",
        nargs="+",
        metavar="FILE_OR_REGEX",
        help="file followed by regexes, or regexes when reading piped input",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source_and_patterns = args.source_and_patterns

    if sys.stdin.isatty():
        if len(source_and_patterns) < 2:
            parser.error("provide a file followed by at least one regex")
        file = Path(source_and_patterns[0])
        patterns = source_and_patterns[1:]
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            parser.error(f"cannot read {file}: {error}")
    else:
        file = Path(source_and_patterns[0])
        if len(source_and_patterns) > 1 and file.is_file():
            patterns = source_and_patterns[1:]
            try:
                text = file.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                parser.error(f"cannot read {file}: {error}")
        else:
            patterns = source_and_patterns
            try:
                text = sys.stdin.read()
            except UnicodeError as error:
                parser.error(f"cannot decode stdin as UTF-8: {error}")

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
