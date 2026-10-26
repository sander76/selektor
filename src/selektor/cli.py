from __future__ import annotations

from .app import run


def main(argv: list[str] | None = None) -> int:
    return run(argv)
