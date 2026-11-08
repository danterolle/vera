from ipaddress import ip_address
from urllib.parse import urlparse

import httpx


def local_server_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or not parsed.hostname or parsed.path not in ("", "/"):
        raise ValueError("The llama-server URL must be a local HTTP origin")
    try:
        loopback = ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname == "localhost"
    if not loopback:
        raise ValueError("The adapter check only permits a loopback llama-server")
    return value.rstrip("/")


def model_id(client: httpx.Client, requested: str | None) -> str:
    response = client.get("/v1/models")
    response.raise_for_status()
    identifiers = [
        item["id"] for item in response.json().get("data", [])
        if isinstance(item.get("id"), str)
    ]
    if requested:
        if requested not in identifiers:
            raise ValueError(f"Model {requested!r} is not served at this endpoint")
        return requested
    if len(identifiers) != 1:
        raise ValueError("Pass --model when the server does not expose exactly one model")
    return identifiers[0]


def adapter_id(client: httpx.Client, requested: int | None) -> tuple[int, float]:
    response = client.get("/lora-adapters")
    response.raise_for_status()
    adapters = response.json()
    if requested is None:
        if len(adapters) != 1:
            raise ValueError("Pass --adapter-id when the server has zero or multiple adapters")
        adapter = adapters[0]
    else:
        adapter = next((item for item in adapters if item["id"] == requested), None)
        if adapter is None:
            raise ValueError(f"LoRA adapter {requested} is not loaded")
    return int(adapter["id"]), float(adapter["scale"])


def set_adapter_scale(client: httpx.Client, identifier: int, scale: float) -> None:
    response = client.post("/lora-adapters", json=[{"id": identifier, "scale": scale}])
    response.raise_for_status()
    adapters = client.get("/lora-adapters")
    adapters.raise_for_status()
    current = next(item for item in adapters.json() if item["id"] == identifier)
    if float(current["scale"]) != scale:
        raise RuntimeError(f"Failed to set LoRA scale to {scale}")
