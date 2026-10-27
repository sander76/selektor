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

import pytest

from selektor.app import find_matches


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = Path(__file__).with_name("test_input.txt")
HAS_TERMINAL = os.name == "posix" and Path("/dev/tty").exists()


def test_matches_multiple_regexes_in_input_order() -> None:
    matches = find_matches([r"c.t", r"b.."], "bar cat bat")

    assert [match.group(0) for match in matches] == ["bar", "cat", "bat"]


@pytest.mark.skipif(not HAS_TERMINAL, reason="requires a Unix terminal")
@pytest.mark.parametrize("use_pipe", [True, False], ids=["piped-stdin", "file-argument"])
def test_selects_match_and_writes_only_to_stdout(use_pipe: bool) -> None:
    source = INPUT_FILE.read_bytes()
    expected = b"another_file.py\n"
    stdout_read, stdout_write = os.pipe()
    pid, terminal_fd = pty.fork()

    if pid == 0:
        os.close(stdout_read)
        os.dup2(stdout_write, 1)
        os.close(stdout_write)
        if use_pipe:
            input_read, input_write = os.pipe()
            os.write(input_write, source)
            os.close(input_write)
            os.dup2(input_read, 0)
            os.close(input_read)

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [str(PROJECT_ROOT / "src"), env.get("PYTHONPATH", "")]
        )
        env["TERM"] = "xterm"
        patterns = [r"some_file\.py", r"another_file\.py"]
        arguments = patterns if use_pipe else [str(INPUT_FILE), *patterns]
        os.execve(sys.executable, [sys.executable, "-m", "selektor", *arguments], env)

    os.close(stdout_write)
    fcntl.ioctl(terminal_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    terminal_output = bytearray()
    selected_output = bytearray()
    sent_next = False
    sent_enter = False
    output_size_after_next = 0
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

            if not sent_next and b"Match 1/2" in terminal_output:
                os.write(terminal_fd, b"n")
                sent_next = True
                output_size_after_next = len(terminal_output)
            if (
                sent_next
                and not sent_enter
                and len(terminal_output) > output_size_after_next
            ):
                os.write(terminal_fd, b"\r")
                sent_enter = True

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
        assert sent_next
        assert sent_enter
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
