import json

from vera.knowledge_graph.models import Entity


def put_entity(conn, value: Entity) -> None:
    """Refresh descriptive names; reference-only nodes cannot erase a known name."""
    rows = conn.execute(
        "MATCH (e:Entity {id: $id}) RETURN e.name, e.aliases", {"id": value.id}
    ).get_all()
    aliases = set(value.aliases)
    name = value.name
    code = value.id.rsplit(":", 1)[-1]
    if rows:
        old_name, old_aliases = rows[0]
        aliases.update(json.loads(old_aliases or "[]"))
        if name in {value.id, code}:
            name = old_name
        elif old_name not in {value.id, code, name}:
            aliases.add(old_name)
    aliases.update((code, name))
    conn.execute(
        "MERGE (e:Entity {id: $id}) SET e.kind = $kind, e.name = $name, e.aliases = $aliases",
        {"id": value.id, "kind": value.kind, "name": name, "aliases": json.dumps(sorted(aliases))},
    ).close()
