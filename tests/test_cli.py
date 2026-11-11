import curses
import fcntl
import os
import pty
import select
import signal
import struct
import sys
import termios
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from selektor.app import run
from selektor.matching import find_matches
from selektor.terminal import LineCollection, browse_on_terminal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = Path(__file__).with_name("test_input.txt")
HAS_TERMINAL = os.name == "posix" and Path("/dev/tty").exists()


def test_matches_multiple_regexes_in_input_order() -> None:
    matches = find_matches([r"c.t", r"b.."], "bar cat bat")

    assert [match.match.group(0) for match in matches] == ["bar", "cat", "bat"]


def test_ignores_zero_width_matches() -> None:
    matches = find_matches([r"(?=a)", "a"], "a")

    assert [match.match.group(0) for match in matches] == ["a"]


def test_line_collection_tracks_matches_and_selection() -> None:
    text = "foo bar\nfoo"
    matches = find_matches(["foo", "bar"], text)
    collection = LineCollection(text, matches)
    first, second, third = collection.matches

    assert collection.lines[0].matches == [first, second]
    assert collection.lines[1].matches == [third]
    assert third.selected

    collection.select_next()
    assert first.selected
    assert not third.selected

    collection.select_previous()
    assert third.selected
    assert not first.selected

    collection.select_previous()
    assert second.selected
    assert collection.selected_line_index == 0
    assert collection.selected_text == "bar"


def test_initial_terminal_view_selects_last_match_and_shows_bottom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Screen:
        def __init__(self) -> None:
            self.rendered: list[tuple[int, str]] = []

        def getmaxyx(self) -> tuple[int, int]:
            return 4, 40

        def erase(self) -> None:
            pass

        def addstr(self, row: int, column: int, text: str, attribute: int) -> None:
            self.rendered.append((row, text))

        def addnstr(
            self, row: int, column: int, text: str, width: int, attribute: int
        ) -> None:
            pass

        def refresh(self) -> None:
            pass

        def keypad(self, enabled: bool) -> None:
            pass

        def getch(self) -> int:
            return 10

    text = "line 0\nline 1\nline 2\nline 3\nlast match"
    collection = LineCollection(text, find_matches(["line 0", "last match"], text))
    screen = Screen()
    monkeypatch.setattr("selektor.terminal.curses.wrapper", lambda run: run(screen))
    monkeypatch.setattr("selektor.terminal.curses.has_colors", lambda: False)
    monkeypatch.setattr("selektor.terminal.curses.curs_set", lambda visibility: None)
    monkeypatch.setattr("selektor.terminal.ensure_color_terminal", lambda: None)
    monkeypatch.setattr("selektor.terminal.configure_curses_colors", lambda: None)

    assert browse_on_terminal(collection) == "last match"
    assert screen.rendered == [(0, "line 3"), (1, "last match")]


def test_line_render_uses_selected_match_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "foo bar"
    collection = LineCollection(text, find_matches(["foo", "bar"], text))
    screen = Mock()
    monkeypatch.setattr("selektor.terminal.curses.color_pair", lambda pair: pair)

    collection.lines[0].render(screen, 0, len(text), True)

    rendered = [(call.args[2], call.args[3]) for call in screen.addstr.call_args_list]
    assert rendered == [
        ("foo", 1 | curses.A_BOLD),
        (" ", curses.A_NORMAL),
        ("bar", 2 | curses.A_UNDERLINE),
    ]


def test_dash_argument_reads_stdin_even_when_stdin_is_a_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin = Mock()
    stdin.isatty.return_value = True
    stdin.read.return_value = "a match"
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(
        "selektor.app.browse",
        lambda text, patterns: "match",
    )

    assert run(["-", "match"]) == 0
    assert capsys.readouterr().out == "match\n"


@pytest.mark.parametrize("argv", [[], ["-"]])
def test_source_and_regex_arguments_are_required(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        run(argv)

    assert error.value.code == 2


@pytest.mark.skipif(not HAS_TERMINAL, reason="requires a Unix terminal")
@pytest.mark.parametrize("input_mode", ["stdin-marker", "file-argument"])
@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (b"\r", b"another_file.py\n"),
        (b"op", b"vim another_file.py\n"),
    ],
    ids=["select", "open-in-vim"],
)
def test_selects_match_and_writes_only_to_stdout(
    input_mode: str, keys: bytes, expected: bytes
) -> None:
    source = INPUT_FILE.read_bytes()
    stdout_read, stdout_write = os.pipe()
    pid, terminal_fd = pty.fork()

    if pid == 0:
        os.close(stdout_read)
        os.dup2(stdout_write, 1)
        os.close(stdout_write)
        if input_mode == "stdin-marker":
            input_read, input_write = os.pipe()
            os.write(input_write, source)
            os.close(input_write)
            os.dup2(input_read, 0)
            os.close(input_read)

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [str(PROJECT_ROOT / "src"), env.get("PYTHONPATH", "")]
        )
        env["TERM"] = "xterm-256color"
        patterns = [r"some_file\.py", r"another_file\.py"]
        if input_mode == "stdin-marker":
            arguments = ["-", *patterns]
        else:
            arguments = [str(INPUT_FILE), *patterns]
        os.execve(sys.executable, [sys.executable, "-m", "selektor", *arguments], env)

    os.close(stdout_write)
    fcntl.ioctl(terminal_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    terminal_output = bytearray()
    selected_output = bytearray()
    sent_shortcut = False
    status = None
    deadline = time.monotonic() + 10

    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([terminal_fd, stdout_read], [], [], 0.05)
            if terminal_fd in ready:
                try:
                    terminal_output.extend(os.read(terminal_fd, 8192))
                except OSError:
                    pass
            if stdout_read in ready:
                chunk = os.read(stdout_read, 4096)
                if chunk:
                    selected_output.extend(chunk)

            if not sent_shortcut and b"Match 2/2" in terminal_output:
                os.write(terminal_fd, keys)
                sent_shortcut = True

            waited, result = os.waitpid(pid, os.WNOHANG)
            if waited:
                status = os.waitstatus_to_exitcode(result)
                break

        if status is None:
            pytest.fail(
                "selektor did not exit after selecting a match; "
                f"terminal output: {bytes(terminal_output[-500:])!r}; "
                f"stdout: {bytes(selected_output)!r}"
            )

        while True:
            try:
                chunk = os.read(stdout_read, 4096)
            except BlockingIOError:
                break
            if not chunk:
                break
            selected_output.extend(chunk)

        assert status == 0
        assert sent_shortcut
        assert selected_output == expected
    finally:
        if status is None:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
        os.close(terminal_fd)
        os.close(stdout_read)
