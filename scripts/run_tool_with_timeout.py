#!/usr/bin/env python3
"""Delegate timeout-wrapped tool execution to the TheKnowledge implementation."""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        str(
            Path(__file__).resolve().parent.parent
            / "TheKnowledge"
            / "scripts"
            / "run_tool_with_timeout.py"
        ),
        run_name="__main__",
    )
