from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import Request


def is_loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def permits_local_request(request: Request) -> bool:
    try:
        parsed_host = urlsplit(f"http://{request.headers.get('host', '')}")
        hostname = parsed_host.hostname
        port = parsed_host.port
    except ValueError:
        return False
    if (
        parsed_host.username is not None
        or port == 0
        or parsed_host.path
        or parsed_host.query
        or parsed_host.fragment
    ):
        return False
    client = request.client.host if request.client else None
    if not is_loopback(hostname) or not is_loopback(client):
        return False
    origin = request.headers.get("origin")
    if origin is None:
        return True
    parsed = urlsplit(origin)
    return (
        parsed.scheme == request.url.scheme
        and parsed.netloc.lower() == request.headers["host"].lower()
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )
