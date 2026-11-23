import json
from collections.abc import Callable

from vera.errors import ProviderError

PROBE_SCHEMA = {
    "type": "object",
    "properties": {"ready": {"type": "boolean"}},
    "required": ["ready"],
    "additionalProperties": False,
}


def check_model_response(complete: Callable[[str, str, dict], str]) -> bool:
    try:
        answer = json.loads(complete(
            'Return {"ready":true}.',
            "Respond with the requested JSON object only.",
            PROBE_SCHEMA,
        ))
    except (ProviderError, TypeError, ValueError):
        return False
    return isinstance(answer, dict) and set(answer) == {"ready"} and answer["ready"] is True
