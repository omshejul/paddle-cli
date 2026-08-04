from __future__ import annotations

import re
import shlex
from pathlib import Path

from paddle_cli.cli import build_parser


def test_documented_site_commands_match_the_cli() -> None:
    html = Path("site/index.html").read_text()
    commands = re.findall(r'data-cli-command="([^"]+)"', html)

    assert commands
    parser = build_parser()
    for command in commands:
        executable, *arguments = shlex.split(command)
        assert executable == "paddle"
        parser.parse_args(arguments)
