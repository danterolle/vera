from fastapi.responses import Response

from vera.data import resource

ASSETS = {
    "knowledge.css": ("web/knowledge/style.css", "text/css; charset=utf-8"),
    "knowledge.js": ("web/knowledge/app.js", "text/javascript; charset=utf-8"),
    "knowledge-layout.js": ("web/knowledge/layout.js", "text/javascript; charset=utf-8"),
    "knowledge-renderer.js": ("web/knowledge/renderer.js", "text/javascript; charset=utf-8"),
    "knowledge-inspector.js": ("web/knowledge/inspector.js", "text/javascript; charset=utf-8"),
    "chat.css": ("web/chat/style.css", "text/css; charset=utf-8"),
    "chat.js": ("web/chat/app.js", "text/javascript; charset=utf-8"),
    "chat-render.js": ("web/chat/render.js", "text/javascript; charset=utf-8"),
    "chat-store.js": ("web/chat/store.js", "text/javascript; charset=utf-8"),
    "routes.js": ("web/shared/routes.js", "text/javascript; charset=utf-8"),
    "viewport.js": ("web/shared/viewport.js", "text/javascript; charset=utf-8"),
}


def load_asset(name: str) -> Response:
    if name not in ASSETS:
        raise KeyError(name)
    path, media_type = ASSETS[name]
    content = resource(path).read_text(encoding="utf-8")
    return Response(content, media_type=media_type)


def load_page(folder: str) -> Response:
    if folder not in {"chat", "knowledge"}:
        raise ValueError("Unknown page")
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
