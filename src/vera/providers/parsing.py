import json


def json_object(content: str) -> dict:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        raise json.JSONDecodeError("No JSON object found", content, 0)
    value = json.loads(content[start:end + 1])
    if not isinstance(value, dict):
        raise json.JSONDecodeError("Expected a JSON object", content, start)
    return value
