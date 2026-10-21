import asyncio
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import httpx
import pytest

from vera.interfaces.api import create_app
from vera.interfaces.assets import load_asset, load_graph_page


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = {}
        self.assets = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            assert attributes["id"] not in self.ids
            self.ids[attributes["id"]] = tag, attributes
        for name in ("src", "href"):
            if attributes.get(name, "").startswith("/assets/"):
                self.assets.add(attributes[name])


def test_review_page_exposes_distinct_unpublished_controls():
    page = Elements()
    response = load_graph_page()
    page.feed(response.body.decode())
    assert response.status_code == 200
    assert {"review-list", "review-refresh", "review-draft", "review-feedback",
            "review-form", "review-details", "review-status"} <= page.ids.keys()
    assert page.ids["review-draft"][1]["hidden"] is None
    assert page.ids["review-retry"][1]["hidden"] is None
    assert page.ids["review-revise"][1]["value"] == "revise"
    assert page.ids["review-status"][1]["role"] == "status"
    assert page.ids["review-feedback"][1]["maxlength"] == "4000"
    assert "/assets/graph-review.css" in page.assets
    assert "/assets/graph.js" in page.assets
    assert page.ids["analysis-result"][1]["hidden"] is None
    assert page.ids["run"][0] == "select" and page.ids["graph"][1]["viewbox"] == "0 0 1200 980"


def test_review_assets_are_served_and_render_untrusted_text_safely():
    for name in ("graph-review.css", "graph-review.js", "graph-review-render.js",
                 "graph-review-request.js", "graph-analysis-report.js"):
        assert load_asset(name).status_code == 200
    renderer = load_asset("graph-review-render.js").body.decode()
    controller = load_asset("graph-review.js").body.decode()
    request = load_asset("graph-review-request.js").body.decode()
    analysis = load_asset("graph-analysis.js").body.decode()
    app = load_asset("graph.js").body.decode()
    assert "innerHTML" not in renderer + controller + request + analysis
    assert "textContent" in renderer
    assert '["https:", "http:"]' in renderer
    assert "noopener noreferrer" in renderer
    assert "supporting_quote" in renderer and "source.content" in renderer
    assert 'response.status === 202' in analysis
    assert 'response.status === 200' in analysis
    assert 'fetch("/v1/reviews")' in controller
    assert "/decisions" in request and "JSON.stringify(decision)" in request
    assert "crypto.randomUUID()" in controller
    assert "retry_decision" in controller and "retry_decision" in renderer
    assert "error.status === 409" in controller
    assert "review.clear()" in app and "initializeReview" in app
    assert 'runSelect.value = ""' in app
    preview = app.split("function pathPreview(", 1)[1].split("function draw(", 1)[0]
    assert '"review_assess"' in preview and "height: 980" in app
    assert all(f'"{node}"' not in preview for node in ("review_wait", "revise"))


def test_review_asset_routes_and_browser_imports_resolve(settings):
    async def exercise():
        transport = httpx.ASGITransport(app=create_app(settings=settings))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            response = await client.get("/graph")
            assert response.status_code == 200
            page = Elements()
            page.feed(response.text)
            pending = list(page.assets)
            visited = set()
            while pending:
                url = pending.pop()
                if url in visited:
                    continue
                asset = await client.get(url)
                assert asset.status_code == 200, url
                assert asset.headers["content-type"].startswith(
                    "text/javascript" if url.endswith(".js") else "text/css"
                )
                visited.add(url)
                if url.endswith(".js"):
                    pending.extend(re.findall(r'from "(/assets/[^"]+)"', asset.text))
            assert {f"/assets/{name}" for name in (
                "graph-review.css", "graph-review.js", "graph-review-render.js",
                "graph-review-request.js", "graph-analysis-report.js"
            )} <= visited

    asyncio.run(exercise())


@pytest.mark.skipif(not shutil.which("node"), reason="Node is not installed")
def test_review_browser_response_and_decision_paths():
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        ["node", "tests/integration/review_ui_smoke.cjs"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
