"""Console output that never crashes a command.

A model answer or a task can hold any character. On Windows the console, or a file the output is redirected to, often uses
cp1252, which cannot show `≤` or an arrow: Python then raises UnicodeEncodeError in the middle of `print`, after the work
is done and saved. This switches stdout and stderr to print a `?` for such a character instead. The encoding stays as it
was, the exit code is unchanged, and a stream that cannot be switched is left alone.
"""
import sys


def tolerate_encoding():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            continue
