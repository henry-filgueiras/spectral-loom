"""The unit suite must stay runnable with no network and no model weights.

These are the tests that fail if someone removes the guard, so they are the
enforcement of `archaeology/decisions/0007` rather than a restatement of it.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.netguard import NetworkAccessError

REPOSITORY = Path(__file__).resolve().parents[1]


def _run_pytest(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Run a nested pytest over `path` under this project's real configuration."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "tests.netguard",
            "-c",
            str(REPOSITORY / "pyproject.toml"),
            "--rootdir",
            str(REPOSITORY),
            str(path),
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=REPOSITORY,
        check=False,
    )


def test_outbound_connections_are_refused() -> None:
    with pytest.raises(NetworkAccessError) as raised:
        socket.create_connection(("huggingface.co", 443), timeout=0.1)
    assert "huggingface.co:443" in str(raised.value)


def test_outbound_connections_are_refused_on_a_raw_socket() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client,
        pytest.raises(NetworkAccessError),
    ):
        client.connect(("huggingface.co", 443))


def test_loopback_still_works() -> None:
    """A local listener is not the network, and the guard must not break it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname(), timeout=1) as client:
            accepted, _ = listener.accept()
            with accepted:
                client.sendall(b"local")
                assert accepted.recv(5) == b"local"


def test_model_dependent_tests_are_deselected_by_default(tmp_path: Path) -> None:
    module = tmp_path / "test_marked.py"
    module.write_text(
        "import pytest\n\n"
        "@pytest.mark.needs_model\n"
        "def test_wants_weights() -> None:\n"
        "    raise AssertionError('ran without model weights')\n\n"
        "def test_ordinary() -> None:\n"
        "    assert True\n",
        encoding="utf-8",
    )
    result = _run_pytest(module)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert "1 deselected" in result.stdout


def test_needs_network_marker_lifts_the_guard(tmp_path: Path) -> None:
    """The escape hatch exists, and reaching it takes an explicit selection."""
    module = tmp_path / "test_marked_network.py"
    module.write_text(
        "import socket\n"
        "import pytest\n"
        "from tests.netguard import NetworkAccessError\n\n"
        "@pytest.mark.needs_network\n"
        "def test_reaches_out() -> None:\n"
        # TEST-NET-1 (RFC 5737) routes nowhere, so this fails as a timeout or a
        # refusal — never as the guard, which is the point being asserted.
        "    try:\n"
        "        socket.create_connection(('192.0.2.1', 9), timeout=0.05).close()\n"
        "    except NetworkAccessError:\n"
        "        raise AssertionError('guard still installed')\n"
        "    except OSError:\n"
        "        pass\n",
        encoding="utf-8",
    )
    deselected = _run_pytest(module)
    assert "1 deselected" in deselected.stdout

    selected = _run_pytest(module, "-m", "needs_network")
    assert selected.returncode == 0, selected.stdout + selected.stderr
    assert "1 passed" in selected.stdout


# ---------------------------------------------------------------------------
# The two workflows are two different promises.
# ---------------------------------------------------------------------------

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _without_comments(path: Path) -> str:
    """A workflow's steps, without the prose explaining them.

    Both files talk *about* `needs_model` and about downloading weights, at
    length, because that is where the reasons live. Only what the runner will
    actually execute is being asserted on here.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def test_pr_ci_stays_hermetic() -> None:
    """CI must not acquire a step that downloads a model or reaches out.

    Asserted against the file rather than trusted, because the offline
    environment variables in it are the only thing standing between a stray hub
    call and a runner quietly pulling eleven gigabytes.
    """
    ci = _without_comments(WORKFLOWS / "ci.yml")
    assert "HF_HUB_OFFLINE" in ci
    for forbidden in (
        "bootstrap_cabinet.py",
        "smoke_cabinet.py",
        "check_cabinet_remote.py",
        "--extra cabinet",
        "needs_model",
        "needs_network",
    ):
        assert forbidden not in ci, f"hermetic CI grew a step that needs {forbidden!r}"


def test_the_availability_sentinel_is_a_separate_scheduled_workflow() -> None:
    """The explicitly networked check does not live in the hermetic one."""
    sentinel = _without_comments(WORKFLOWS / "cabinet-availability.yml")
    assert "schedule:" in sentinel
    assert "cron:" in sentinel
    assert "check_cabinet_remote.py" in sentinel
    assert "contents: read" in sentinel, "a monitor mutates nothing"

    for forbidden in ("bootstrap_cabinet.py", "smoke_cabinet.py", "--extra cabinet"):
        assert forbidden not in sentinel, f"the sentinel would fetch or run a model: {forbidden!r}"
