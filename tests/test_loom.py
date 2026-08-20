"""Tests for the `loom` entry point.

The router exists to hold one fact — which environment each command needs — in
one place instead of in someone's memory. The risk that creates is drift: a new
`spectral-loom` subcommand lands, nobody thinks about the wrapper, and the
project now has a documented entry point that silently cannot reach part of its
own CLI.

So the test that matters here is completeness, asserted against argparse rather
than against a list someone maintained by hand. The rest is the shape of a thing
that routes: it forwards, it refuses when a precondition is missing, and it does
not grow behaviour of its own.

Hermetic, like everything else. These run `/bin/sh` on the script and never
invoke `uv`, the network, or a model.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from spectral_loom.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]
LOOM = REPO_ROOT / "loom"


def loom_commands() -> list[str]:
    """The router's own declaration of what it routes."""
    match = re.search(r'^LOOM_COMMANDS="([^"]+)"', LOOM.read_text(), re.MULTILINE)
    assert match, "loom must declare LOOM_COMMANDS on a single line"
    return match.group(1).split()


def cli_subcommands() -> list[str]:
    """Every subcommand `spectral-loom` actually has, from argparse itself."""
    for action in build_parser()._subparsers._group_actions:  # type: ignore[union-attr]
        if action.choices:
            return list(action.choices)
    raise AssertionError("spectral-loom has no subparsers")


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", str(LOOM), *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        check=False,
    )


def test_loom_is_executable() -> None:
    assert LOOM.is_file()
    assert LOOM.stat().st_mode & 0o111, "loom must be executable, or `./loom` is a lie"
    assert LOOM.read_text().startswith("#!/bin/sh\n")


def test_loom_is_valid_shell() -> None:
    """Nothing else in this repository checks shell syntax, so this does."""
    syntax = subprocess.run(["/bin/sh", "-n", str(LOOM)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr


def test_every_cli_subcommand_is_reachable_from_the_router() -> None:
    """The drift guard, and the reason this file exists.

    A new `spectral-loom` subcommand that the router cannot reach makes the
    documented entry point incomplete, which is worse than having no wrapper at
    all: it looks like the whole surface and is not.
    """
    missing = set(cli_subcommands()) - set(loom_commands())
    assert not missing, f"loom does not route: {sorted(missing)}"


def test_the_router_dispatches_everything_it_declares() -> None:
    """And the reverse: nothing declared falls through to the error branch."""
    body = LOOM.read_text()
    dispatched = set(re.findall(r"^    ([a-z |-]+?)\)$", body, re.MULTILINE))
    handled: set[str] = set()
    for arm in dispatched:
        handled.update(part.strip() for part in arm.split("|"))
    undispatched = set(loom_commands()) - handled
    assert not undispatched, f"declared but not dispatched: {sorted(undispatched)}"


def test_help_lists_every_command() -> None:
    result = run("help")
    assert result.returncode == 0
    for command in loom_commands():
        if command == "help":
            continue
        assert command in result.stdout, f"{command} is routed but undocumented in help"


def test_bare_invocation_is_help_not_an_error() -> None:
    result = run()
    assert result.returncode == 0
    assert "one entry point" in result.stdout


def test_an_unknown_command_names_itself_and_fails() -> None:
    """`separate` used to be the example here, and then it was implemented.

    The replacement is a verb this project has decided it will not have: the
    projections are gates 6 and 7 and they are not a `loom` command yet.
    """
    result = run("render")
    assert result.returncode != 0
    assert "unknown command: render" in result.stderr
    assert "doctor" in result.stderr, "say what does exist"


def test_an_unknown_bootstrap_subcommand_fails(tmp_path: Path) -> None:
    result = run("bootstrap", "fetch")
    assert result.returncode != 0
    assert "env, assets, or status" in result.stderr


def test_bootstrap_without_a_subcommand_fails() -> None:
    result = run("bootstrap")
    assert result.returncode != 0
    assert "needs a subcommand" in result.stderr


@pytest.mark.parametrize(
    ("command", "arguments"),
    [("generate", ["spec.yaml"]), ("smoke", []), ("bootstrap", ["assets"])],
)
def test_cabinet_commands_refuse_rather_than_build(
    tmp_path: Path, command: str, arguments: list[str]
) -> None:
    """A missing cabinet prints the command that builds it and stops there.

    It does not start an eleven-gigabyte download because you asked for
    something else. Preconditions in this project are established deliberately.
    """
    copy = tmp_path / "loom"
    copy.write_text(LOOM.read_text(), encoding="utf-8")
    result = subprocess.run(
        ["/bin/sh", str(copy), command, *arguments],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 1
    assert "cabinet environment is not built" in result.stderr
    assert "./loom bootstrap env" in result.stderr
    assert not (tmp_path / ".venv-cabinet").exists(), "refusing means not building"
    assert not (tmp_path / "models").exists()


def test_the_router_does_not_reimplement_the_cli() -> None:
    """It forwards and execs, so the underlying exit code is the exit code.

    A wrapper that returned its own status would break `spectral-loom`'s
    documented interface from the outside, where nothing in the CLI's own tests
    would ever see it.
    """
    body = LOOM.read_text()
    execs = [line.strip() for line in body.splitlines() if line.strip().startswith("exec ")]
    assert execs, "nothing is routed"

    for line in execs:
        forwards = '"$@"' in line
        continued = line.endswith("\\")  # forwarding is on the next line
        assert forwards or continued, f"arguments not forwarded: {line}"

    # `$*` re-splits on whitespace, so a spec path containing a space would
    # silently become two arguments. The router must hand on exactly what it was
    # handed. (`die` uses `$*` legitimately: that joins a message, not a list.)
    assert not [line for line in execs if "$*" in line]

    # Everything that reaches a program `exec`s into it, so the program's exit
    # code is the exit code. `help` prints and `check` is a sequence; those two
    # are the router's own, and they are the only arms that end without one.
    routed_bodies = body.split('case "$command" in', 1)[1].split("\n    *)", 1)[0]
    arms = [arm for arm in routed_bodies.split("\n        ;;") if arm.strip()]
    without_exec = [arm.strip().splitlines()[0].strip() for arm in arms if "exec " not in arm]
    assert without_exec == ["help | --help | -h)", "check)"]
