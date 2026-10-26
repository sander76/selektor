from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .terminal import browse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Browse regex matches in a file or piped input. "
            "When FILE is omitted, read text from stdin."
        )
    )
    parser.add_argument(
        "source_or_regex",
        help="file to search, or regex when reading piped input",
    )
    parser.add_argument(
        "regex",
        nargs="?",
        help="regular expression to match (omit when reading piped input)",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.regex is None:
        if sys.stdin.isatty():
            parser.error("provide a file, or pipe text to stdin with a regex")
        pattern = args.source_or_regex
        try:
            text = sys.stdin.read()
        except UnicodeError as error:
            parser.error(f"cannot decode stdin as UTF-8: {error}")
    else:
        file = Path(args.source_or_regex)
        pattern = args.regex
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            parser.error(f"cannot read {file}: {error}")

    try:
        matches = list(re.finditer(pattern, text))
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
