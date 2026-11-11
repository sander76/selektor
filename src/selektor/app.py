from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .terminal import browse


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
        selected_text = browse(text, patterns)
    except re.error as error:
        parser.error(f"invalid regular expression: {error}")
    except RuntimeError as error:
        parser.error(str(error))

    if selected_text is None:
        return 1

    print(selected_text)
    return 0
