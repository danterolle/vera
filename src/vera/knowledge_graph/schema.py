import json

VERSION = 2
TABLES = ("Entity", "SourceRecord", "Assertion", "Run", "Alert", "Event")
STATEMENTS = (
    "CREATE NODE TABLE GraphMeta(id STRING, version INT64, PRIMARY KEY(id))",
    "CREATE NODE TABLE Entity(id STRING, kind STRING, name STRING, aliases STRING, "
    "PRIMARY KEY(id))",
    "CREATE NODE TABLE SourceRecord(record_key STRING, evidence_id STRING, source STRING, "
    "status STRING, url STRING, content STRING, payload_json STRING, title STRING, "
    "PRIMARY KEY(record_key))",
    "CREATE NODE TABLE Assertion(id STRING, predicate STRING, status STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Run(id STRING, session_id STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Alert(id STRING, rule_id STRING, status STRING, "
    "payload_json STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Event(id STRING, status STRING, payload_json STRING, PRIMARY KEY(id))",
    "CREATE REL TABLE SUBJECT(FROM Assertion TO Entity)",
    "CREATE REL TABLE OBJECT(FROM Assertion TO Entity)",
    "CREATE REL TABLE SUPPORTED_BY(FROM Assertion TO SourceRecord, "
    "supporting_quote STRING, field_path STRING)",
    "CREATE REL TABLE DESCRIBES(FROM SourceRecord TO Entity)",
    "CREATE REL TABLE USED_RECORD(FROM Run TO SourceRecord)",
    "CREATE REL TABLE HAS_ALERT(FROM Run TO Alert)",
    "CREATE REL TABLE HAS_EVENT(FROM Run TO Event)",
    "CREATE REL TABLE TRIGGERED_BY(FROM Alert TO Event)",
    "CREATE REL TABLE SUGGESTS(FROM Alert TO Entity, status STRING)",
)


def migrate(connection) -> None:
    tables = connection.execute("CALL show_tables() RETURN name").get_all()
    if tables:
        versions = connection.execute("MATCH (m:GraphMeta) RETURN m.version").get_all()
        if versions == [[1]]:
            upgrade_v1(connection)
        check_version(connection)
        return
    for statement in STATEMENTS:
        connection.execute(statement).close()
    connection.execute("CREATE (:GraphMeta {id: 'schema', version: $v})", {"v": VERSION}).close()


def check_version(connection) -> None:
    rows = connection.execute("MATCH (m:GraphMeta {id: 'schema'}) RETURN m.version").get_all()
    if rows != [[VERSION]]:
        raise ValueError("Unsupported Kuzu schema version; run vera kg-build to upgrade version 1")


def upgrade_v1(connection) -> None:
    """Preserve existing sources, assertions, and runs during the explicit build."""
    connection.execute("BEGIN TRANSACTION").close()
    try:
        connection.execute("ALTER TABLE Entity ADD aliases STRING DEFAULT '[]'").close()
        connection.execute("ALTER TABLE SourceRecord ADD title STRING DEFAULT ''").close()
        records = connection.execute(
            "MATCH (r:SourceRecord) RETURN r.record_key, r.payload_json"
        ).get_all()
        for key, raw in records:
            connection.execute(
                "MATCH (r:SourceRecord {record_key: $key}) SET r.title = $title",
                {"key": key, "title": json.loads(raw)["title"]},
            ).close()
        connection.execute("MATCH (m:GraphMeta) SET m.version = $v", {"v": VERSION}).close()
        connection.execute("COMMIT").close()
    except Exception:
        connection.execute("ROLLBACK").close()
        raise
