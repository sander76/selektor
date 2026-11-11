from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Matcher:
    pattern: str
    transformer: Callable[[str], str]


def open_in_vim(match: str) -> str:
    parts = match.split(":")
    match len(parts):
        case 1:
            return f"vim {parts[0]}"
        case 2:
            return f"vim +{parts[1]} {parts[0]}"
        case 3:
            return f"vim +call cursor({parts[1]},{parts[2]}) {parts[0]}"
    return f"vim {match}"


def open_in_pycharm(match: str) -> str:
    parts = match.split(":")
    match len(parts):
        case 1:
            return f"pycharm {parts[0]}"
        case 2:
            return f"pycharm --line {parts[1]} {parts[0]}"
        case 3:
            return f"pycharm --line {parts[1]} --column {parts[2]} {parts[0]}"
    return f"pycharm {match}"
