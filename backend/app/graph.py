"""FalkorDB connection, index creation, and bulk loading of data/seed.json."""
import json
import os
import pathlib

from dotenv import load_dotenv

load_dotenv()

GRAPH_NAME = os.getenv("GRAPH_NAME", "orgmind")
LABELS = ["Person", "Team", "Service", "Project", "Document", "Ticket", "Message", "Topic", "Decision"]
SEED_PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "seed.json"

_db = None


def get_db():
    global _db
    if _db is None:
        from falkordb import FalkorDB  # lazy: unit tests run without the client installed
        _db = FalkorDB(
            host=os.getenv("FALKORDB_HOST", "localhost"),
            port=int(os.getenv("FALKORDB_PORT", "6379")),
            username=os.getenv("FALKORDB_USERNAME") or None,
            password=os.getenv("FALKORDB_PASSWORD") or None,
            ssl=os.getenv("FALKORDB_SSL", "false").lower() == "true",
        )
    return _db


def get_graph():
    return get_db().select_graph(GRAPH_NAME)


def run(query: str, params: dict | None = None) -> list[dict]:
    """Run a Cypher query, return rows as dicts keyed by the RETURN aliases."""
    res = get_graph().query(query, params or {})
    header = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
    return [dict(zip(header, (_ser(v) for v in row))) for row in res.result_set]


def _ser(v):
    """Make FalkorDB Node/Edge/Path values JSON-safe."""
    if hasattr(v, "labels") and hasattr(v, "properties"):  # Node
        return {"labels": list(v.labels), **v.properties}
    if hasattr(v, "relation") and hasattr(v, "properties"):  # Edge
        return {"relation": v.relation, **v.properties}
    if isinstance(v, list):
        return [_ser(x) for x in v]
    if isinstance(v, dict):
        return {k: _ser(x) for k, x in v.items()}
    return v


def create_indexes() -> None:
    """Index on id for every label, plus Topic.name (PRD section 4)."""
    stmts = [f"CREATE INDEX FOR (n:{l}) ON (n.id)" for l in LABELS] + ["CREATE INDEX FOR (n:Topic) ON (n.name)"]
    g = get_graph()
    for s in stmts:
        try:
            g.query(s)
        except Exception as e:  # index already exists -> fine
            if "already" not in str(e).lower():
                raise


def reset_graph() -> None:
    try:
        get_graph().delete()
    except Exception:
        pass  # graph did not exist yet


def load_seed(path: pathlib.Path = SEED_PATH, batch: int = 500) -> dict:
    """Idempotent bulk load (MERGE) of nodes and edges from seed.json."""
    data = json.loads(pathlib.Path(path).read_text())
    g = get_graph()
    create_indexes()
    for label, rows in data["nodes"].items():
        assert label in LABELS, label
        for i in range(0, len(rows), batch):
            g.query(f"UNWIND $rows AS r MERGE (n:{label} {{id: r.id}}) SET n += r", {"rows": rows[i:i + batch]})
    groups: dict[tuple, list] = {}
    for e in data["edges"]:
        groups.setdefault((e["type"], e["from"][0], e["to"][0]), []).append({"f": e["from"][1], "t": e["to"][1]})
    for (etype, fl, tl), rows in groups.items():
        assert fl in LABELS and tl in LABELS and etype.isupper()
        for i in range(0, len(rows), batch):
            g.query(f"UNWIND $rows AS r MATCH (a:{fl} {{id: r.f}}) MATCH (b:{tl} {{id: r.t}}) MERGE (a)-[:{etype}]->(b)",
                    {"rows": rows[i:i + batch]})
    return {"nodes": {k: len(v) for k, v in data["nodes"].items()}, "edges": len(data["edges"])}
