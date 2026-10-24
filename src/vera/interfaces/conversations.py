import json
from uuid import UUID

from vera.workflow.orchestrator import VeraOrchestrator


def _chat_session(session_id: str | None, origin: str | None) -> bool:
    if not session_id:
        return False
    if origin == "chat":
        return True
    # Chat versions before the origin field used UUID session IDs.
    if origin is None:
        try:
            UUID(session_id)
            return True
        except ValueError:
            pass
    return False


def conversation_history(engine: VeraOrchestrator) -> list[dict]:
    sessions: dict[str, dict] = {}

    def add(session_id, origin, turn):
        if not _chat_session(session_id, origin):
            return
        chat = sessions.setdefault(session_id, {"id": session_id, "turns": []})
        chat["turns"].append(turn)

    with engine.runtime.memory._connect() as conn:
        rows = conn.execute(
            "SELECT id, session_id, query, created_at, "
            "json_extract(result_json, '$.answer') AS answer, "
            "json_extract(result_json, '$.metadata.origin') AS origin "
            "FROM runs ORDER BY created_at DESC LIMIT 1000"
        ).fetchall()
        held = conn.execute(
            "SELECT review_json FROM reviews WHERE status != 'approved' "
            "ORDER BY rowid DESC LIMIT 1000"
        ).fetchall()
    for row in reversed(rows):
        summary = row["answer"].removeprefix("## Assessment\n").split("\n\n## ")[0].strip()
        add(row["session_id"], row["origin"], {
            "run_id": row["id"], "query": row["query"], "summary": summary,
            "kind": "result", "created_at": row["created_at"],
        })
    live = {record.run_id: record for record in engine.list_reviews()}
    for row in reversed(held):
        raw = json.loads(row["review_json"])
        record = live.get(raw["run_id"])
        if record:
            raw = record.model_dump(mode="json")
        origin = raw.get("metadata", {}).get("origin")
        # Old active checkpoints have API as their default but no persisted origin.
        if record and not json.loads(row["review_json"]).get("metadata", {}).get("origin"):
            origin = None
        add(raw.get("session_id"), origin, {
            "run_id": raw["run_id"], "query": raw["query"],
            "summary": raw["draft"]["summary"], "kind": "review",
            "status": raw["status"], "version": raw["version"],
            "created_at": raw.get("created_at"),
        })
    for chat in sessions.values():
        chat["turns"].sort(key=lambda turn: turn["created_at"] or "9999")
        chat["title"] = chat["turns"][0]["query"][:70]
    return list(sessions.values())
