from fastapi.responses import Response

from vera.data import resource

ASSETS = {
    "knowledge.css": ("web/knowledge/style.css", "text/css; charset=utf-8"),
    "knowledge.js": ("web/knowledge/app.js", "text/javascript; charset=utf-8"),
    "knowledge-layout.js": ("web/knowledge/layout.js", "text/javascript; charset=utf-8"),
    "knowledge-renderer.js": ("web/knowledge/renderer.js", "text/javascript; charset=utf-8"),
    "knowledge-inspector.js": ("web/knowledge/inspector.js", "text/javascript; charset=utf-8"),
    "graph.css": ("web/graph/styles/layout.css", "text/css; charset=utf-8"),
    "graph-ui.css": ("web/graph/styles/components.css", "text/css; charset=utf-8"),
    "graph-svg.css": ("web/graph/styles/diagram.css", "text/css; charset=utf-8"),
    "graph-analysis.css": ("web/graph/styles/analysis.css", "text/css; charset=utf-8"),
    "graph-review.css": ("web/graph/styles/review.css", "text/css; charset=utf-8"),
    "graph.js": ("web/graph/scripts/app.js", "text/javascript; charset=utf-8"),
    "graph-analysis.js": ("web/graph/scripts/analysis.js", "text/javascript; charset=utf-8"),
    "graph-analysis-report.js": (
        "web/graph/scripts/analysis-report.js", "text/javascript; charset=utf-8"
    ),
    "graph-review.js": ("web/graph/scripts/review.js", "text/javascript; charset=utf-8"),
    "graph-review-request.js": (
        "web/graph/scripts/review-request.js", "text/javascript; charset=utf-8"
    ),
    "graph-review-render.js": (
        "web/graph/scripts/review-render.js", "text/javascript; charset=utf-8"
    ),
    "graph-panels.js": ("web/graph/scripts/panels.js", "text/javascript; charset=utf-8"),
    "graph-renderer.js": ("web/graph/scripts/renderer.js", "text/javascript; charset=utf-8"),
    "graph-viewport.js": ("web/graph/scripts/viewport.js", "text/javascript; charset=utf-8"),
}


def load_asset(name: str) -> Response:
    if name not in ASSETS:
        raise KeyError(name)
    path, media_type = ASSETS[name]
    content = resource(path).read_text(encoding="utf-8")
    return Response(content, media_type=media_type)


def load_graph_page(*, knowledge: bool = False) -> Response:
    folder = "knowledge" if knowledge else "graph"
    content = resource(f"web/{folder}/index.html").read_text(encoding="utf-8")
    headers = {
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content, media_type="text/html; charset=utf-8", headers=headers)
