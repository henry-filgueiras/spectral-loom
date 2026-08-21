"""The page templates live in files, and that is load-bearing rather than tidy.

Both observatories used to keep their page in a non-raw triple-quoted Python
string. Python decodes such a string at import, so a `\n` written inside
JavaScript became a real newline in the middle of a JS string literal and the
page failed to parse in the browser — twice, in two sessions, with every Python
test passing while nothing executed.

Moving the templates to `.html` files removes the decoding step entirely, so the
bug is not fixed but *unreachable*. These tests hold that property: the files
ship, they are read verbatim, and neither module has grown an embedded template
again.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from spectral_loom import observatory, timeline_observatory
from spectral_loom.observatory import ObservatoryError, load_page

MODULES = (observatory, timeline_observatory)
SOURCE = Path(__file__).resolve().parents[1] / "src" / "spectral_loom"


def test_both_pages_are_present_beside_their_modules() -> None:
    for module in MODULES:
        target = module.PAGES / module.PAGE_TEMPLATE
        assert target.is_file(), target
        assert target.parent == SOURCE / "pages"


def test_a_page_is_read_verbatim() -> None:
    """No decoding step means no way to escape it wrong."""
    for module in MODULES:
        target = module.PAGES / module.PAGE_TEMPLATE
        assert load_page(module.PAGE_TEMPLATE) == target.read_text(encoding="utf-8")


def test_a_missing_page_says_which_file_and_where() -> None:
    with pytest.raises(ObservatoryError, match="page template at"):
        load_page("no-such-page.html")


def test_the_pages_are_whole_documents() -> None:
    for module in MODULES:
        page = load_page(module.PAGE_TEMPLATE)
        assert page.startswith("<!doctype html>")
        assert page.rstrip().endswith("</html>")
        assert page.count("<script>") == page.count("</script>") == 1
        assert page.count("<style>") == page.count("</style>") == 1


def test_neither_module_embeds_a_page_any_more() -> None:
    """The regression guard.

    A template that creeps back into a module source brings the escaping trap
    back with it, and it would pass every other test in this suite.
    """
    for module in MODULES:
        path = SOURCE / f"{Path(module.__file__ or '').name}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "<!doctype html" not in node.value.lower(), (
                    f"{path.name} embeds a page again; put it under "
                    f"src/spectral_loom/pages/ instead"
                )


def test_the_javascript_carries_its_own_escapes() -> None:
    """The exact byte sequence the old arrangement destroyed."""
    page = load_page(timeline_observatory.PAGE_TEMPLATE)
    assert r"join('\n')" in page
    assert "join('\n')" not in page, "a real newline is sitting inside a JS string literal"


# ---------------------------------------------------------------------------
# The page's own references, and why they are relative.
# ---------------------------------------------------------------------------


def test_a_page_references_its_artifacts_relatively() -> None:
    """So the page inherits whatever prefix it was served under.

    An absolute `/audio/bass` makes the browser resolve against the origin root,
    so the request never carries the path the page was served under. Behind a
    prefix — a reverse proxy handing out a capability URL — every such fetch
    escapes the prefix and misses, and the proxy's own path rewriting cannot
    save it: the browser built the URL before the proxy ever saw it.
    """
    from spectral_loom.observatory import page_url

    assert page_url("/audio/bass") == "audio/bass"
    assert page_url("/timeline.json") == "timeline.json"
    assert page_url("audio/bass") == "audio/bass"


def test_the_server_still_routes_on_absolute_paths() -> None:
    """Relative is how the page *asks*; absolute is what arrives on the wire."""
    from spectral_loom.observatory import page_url

    assert page_url("/audio/bass") != "/audio/bass"
    # and the whitelist a server matches against keeps the leading slash
    assert "/" + page_url("/audio/bass") == "/audio/bass"
