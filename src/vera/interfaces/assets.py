from fastapi.responses import Response

from vera.data import resource

ASSETS = {
    "graph.css": ("web/graph/styles/layout.css", "text/css; charset=utf-8"),
    "graph-ui.css": ("web/graph/styles/components.css", "text/css; charset=utf-8"),
    "graph-svg.css": ("web/graph/styles/diagram.css", "text/css; charset=utf-8"),
    "graph.js": ("web/graph/scripts/app.js", "text/javascript; charset=utf-8"),
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


def load_graph_page() -> Response:
    content = resource("web/graph/index.html").read_text(encoding="utf-8")
    headers = {
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content, media_type="text/html; charset=utf-8", headers=headers)
