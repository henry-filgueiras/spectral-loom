"""Hermetic-suite enforcement: the unit tests may not reach the network.

Loaded as a pytest plugin so it can be enabled from the command line (`-p
tests.netguard`) as well as through `tests/conftest.py`. The guard exists because
a test that quietly downloads a model turns a fast local check into a
multi-gigabyte one and makes CI depend on a third party staying up; see
`archaeology/decisions/0007`.

The block is deliberately narrow. Loopback and Unix sockets stay open, because
a test that starts a local listener is doing something local. Anything that
leaves the machine raises.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

#: Addresses a test may still connect to. `0.0.0.0` and `""` appear as the
#: peer address of a loopback listener on some platforms.
LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", ""})

_HINT = (
    "the unit suite is hermetic and must run with no network and no model weights "
    "(archaeology/decisions/0007). Mark the test `needs_network` if it genuinely has "
    "to reach out, or `needs_model` if it needs weights on disk; both are deselected "
    "by default and neither runs in CI."
)


class NetworkAccessError(RuntimeError):
    """Raised when a test tries to open a connection that leaves the machine."""


def _describe(address: Any) -> str:
    if isinstance(address, tuple) and address:
        host = address[0]
        port = address[1] if len(address) > 1 else "?"
        return f"{host}:{port}"
    return str(address)


def _is_local(family: int, address: Any) -> bool:
    if family == getattr(socket, "AF_UNIX", object()):
        return True
    if isinstance(address, tuple) and address:
        return str(address[0]) in LOCAL_HOSTS
    return False


def _refuse(address: Any) -> NetworkAccessError:
    return NetworkAccessError(f"blocked connection to {_describe(address)}: {_HINT}")


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse outbound connections for the duration of every unmarked test."""
    if request.node.get_closest_marker("needs_network") is not None:
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create_connection = socket.create_connection

    def guarded_connect(self: socket.socket, address: Any) -> None:
        if not _is_local(self.family, address):
            raise _refuse(address)
        real_connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: Any) -> int:
        if not _is_local(self.family, address):
            raise _refuse(address)
        return real_connect_ex(self, address)

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        if not _is_local(socket.AF_INET, address):
            raise _refuse(address)
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
