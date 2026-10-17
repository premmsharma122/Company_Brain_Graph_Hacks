"""The Cypher the product depends on, plus thin Python wrappers.

Every wrapper returns {"tool", "cypher", "params", "rows", ...} so the UI (and later the agent)
can show the exact query behind each answer.

NOTE: FalkorDB supports a subset of Cypher. The PRD's queries were adapted to avoid EXISTS{}
subqueries and map-in-list indexing. Run `python -m app.verify_queries` against a live
FalkorDB and fix any dialect errors before relying on them.
"""
from . import graph

# ---- who knows a topic: authored counts 2x, participated 1x ---------------------------------
FIND_EXPERT = """
MATCH (p:Person)-[r:AUTHORED|PARTICIPATED_IN]->(x)-[:ABOUT]->(t:Topic {name: $topic})
RETURN p.id AS person_id, p.name AS person, p.role AS role, p.active AS active,
       sum(CASE WHEN type(r) = 'AUTHORED' THEN 2 ELSE 1 END) AS score,
       count(DISTINCT x) AS evidence, collect(DISTINCT x.id)[..5] AS sources
ORDER BY score DESC LIMIT $limit
"""

# ---- decisions ---------------------------------------------------------------------------------
FIND_DECISIONS = """
MATCH (d:Decision)
WHERE toLower(d.summary) CONTAINS toLower($kw)
RETURN d.id AS id, d.summary AS summary, d.date AS date, d.status AS status
ORDER BY d.date DESC LIMIT 10
"""

TRACE_DECISION = """
MATCH (d:Decision {id: $id})
OPTIONAL MATCH (d)-[:DECIDED_IN]->(src)
OPTIONAL MATCH (d)-[:MADE_BY]->(p:Person)
OPTIONAL MATCH (newer:Decision)-[:SUPERSEDES]->(d)
OPTIONAL MATCH (d)-[:SUPERSEDES]->(older:Decision)
OPTIONAL MATCH (d)-[:AFFECTS]->(a)
RETURN d.id AS id, d.summary AS summary, d.date AS date, d.status AS status,
       p.name AS made_by, p.id AS made_by_id, newer IS NULL AS is_current,
       collect(DISTINCT {id: src.id, kind: labels(src)[0], label: coalesce(src.title, src.text)}) AS sources,
       collect(DISTINCT newer.id) AS superseded_by, collect(DISTINCT older.id) AS supersedes,
       collect(DISTINCT a.name) AS affects, collect(DISTINCT a.id) AS affects_ids
"""

# ---- ownership ---------------------------------------------------------------------------------
GET_OWNER = """
MATCH (t:Team)-[:OWNS]->(s:Service {name: $svc})
OPTIONAL MATCH (m:Person)-[:MEMBER_OF]->(t)
RETURN s.id AS service_id, s.name AS service, s.tier AS tier, s.topic AS topic, t.id AS team_id, t.name AS team,
       collect(DISTINCT {id: m.id, name: m.name, role: m.role, active: m.active}) AS members
"""

# ---- blast radius ------------------------------------------------------------------------------
BLAST_RADIUS = """
MATCH path = (s:Service {name: $svc})<-[:DEPENDS_ON*1..3]-(dep:Service)
OPTIONAL MATCH (t:Team)-[:OWNS]->(dep)
RETURN dep.id AS service_id, dep.name AS service, dep.tier AS tier, t.id AS team_id, t.name AS team, min(length(path)) AS hops
ORDER BY hops, service
"""

# ---- bus factor: topics with exactly one author -------------------------------------------------
BUS_FACTOR = """
MATCH (p:Person)-[:AUTHORED]->(x)-[:ABOUT]->(t:Topic)
WITH t, p, count(x) AS c
WITH t, collect(p.name) AS names, collect(p.active) AS actives, collect(p.id) AS pids, sum(c) AS artifacts
WHERE size(names) = 1
RETURN t.name AS topic, names[0] AS only_author, pids[0] AS author_id, actives[0] AS author_active, artifacts
ORDER BY artifacts DESC
"""

# ---- stale docs: superseded OR written by an inactive person --------------------------------------
STALE_DOCS = """
MATCH (d:Document)
OPTIONAL MATCH (newer:Document)-[:SUPERSEDES]->(d)
OPTIONAL MATCH (p:Person)-[:AUTHORED]->(d)
WITH d, newer, p
WHERE newer IS NOT NULL OR p.active = false
RETURN d.id AS id, d.title AS title, d.date AS date,
       collect(DISTINCT newer.id) AS superseded_by,
       collect(DISTINCT CASE WHEN p.active = false THEN p.name END) AS inactive_authors
ORDER BY d.date
"""

TOPICS = "MATCH (t:Topic) RETURN t.name AS name, t.service AS service ORDER BY name"
SERVICES = "MATCH (s:Service) RETURN s.id AS id, s.name AS name, s.topic AS topic ORDER BY name"
ALL_DECISIONS = "MATCH (d:Decision) RETURN d.id AS id, d.summary AS summary, d.date AS date, d.status AS status ORDER BY d.date"

# ---- node inspect + graph views (UI) ---------------------------------------------------------------
GET_NODE = "MATCH (n {id: $id}) RETURN labels(n)[0] AS kind, n AS node LIMIT 1"
NODE_OUT = """MATCH (n {id: $id})-[r]->(m)
RETURN type(r) AS rel, m.id AS id, labels(m)[0] AS kind, coalesce(m.name, m.title, m.summary, m.text) AS label LIMIT 50"""
NODE_IN = """MATCH (n {id: $id})<-[r]-(m)
RETURN type(r) AS rel, m.id AS id, labels(m)[0] AS kind, coalesce(m.name, m.title, m.summary, m.text) AS label LIMIT 50"""
_G = ("a.id AS a_id, labels(a)[0] AS a_kind, coalesce(a.name, a.title, a.summary, a.text, a.id) AS a_label, "
      "type(r) AS rel, b.id AS b_id, labels(b)[0] AS b_kind, coalesce(b.name, b.title, b.summary, b.text, b.id) AS b_label")
OVERVIEW = f"MATCH (a)-[r:OWNS|DEPENDS_ON]->(b) RETURN {_G}"
SUBGRAPH_LINKS = f"MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids RETURN {_G}"
SUBGRAPH_NODES = "MATCH (a) WHERE a.id IN $ids RETURN a.id AS a_id, labels(a)[0] AS a_kind, coalesce(a.name, a.title, a.summary, a.text, a.id) AS a_label"
SUBGRAPH_EXPAND = f"""MATCH (a)-[r]-(b) WHERE a.id IN $ids AND NOT (labels(b)[0] IN ['Message', 'Ticket', 'Document'])
RETURN {_G} LIMIT 80"""


def _out(tool, cypher, params, rows, **extra):
    return {"tool": tool, "cypher": cypher.strip(), "params": params, "rows": rows, **extra}


def find_expert(topic: str, limit: int = 5):
    p = {"topic": topic, "limit": limit}
    return _out("find_expert", FIND_EXPERT, p, graph.run(FIND_EXPERT, p))


def find_decisions(keyword: str):
    p = {"kw": keyword}
    return _out("find_decisions", FIND_DECISIONS, p, graph.run(FIND_DECISIONS, p))


def trace_decision(decision_id: str):
    p = {"id": decision_id}
    rows = graph.run(TRACE_DECISION, p)
    return _out("trace_decision", TRACE_DECISION, p, rows)


def build_owner_result(owner_rows: list, expert_rows: list) -> dict:
    """Pure: rank active team members by expertise on the service's topic -> primary/backup/warnings."""
    r = owner_rows[0]
    scores = {e["person_id"]: e for e in expert_rows}
    ranked = sorted((m for m in r["members"] if m["active"]), key=lambda m: -scores.get(m["id"], {}).get("score", 0))
    ranked = [{**m, "score": scores.get(m["id"], {}).get("score", 0)} for m in ranked]
    primary = ranked[0] if ranked else None
    backup = ranked[1] if len(ranked) > 1 else None
    warnings = []
    if backup is None:
        warnings.append("No active backup: single point of failure")
    elif primary and backup["score"] < 0.5 * primary["score"]:
        warnings.append(f"Backup {backup['name']} is thin on '{r['topic']}' (score {backup['score']} vs {primary['score']})")
    gone = [m["name"] for m in r["members"] if not m["active"]]
    if gone:
        warnings.append("Inactive former members with knowledge: " + ", ".join(gone))
    return {"primary": primary, "backup": backup, "warnings": warnings}


def get_owner(service: str):
    """Owning team + primary/backup, where expertise on the service's topic decides who is who."""
    p = {"svc": service}
    rows = graph.run(GET_OWNER, p)
    if not rows:
        return _out("get_owner", GET_OWNER, p, [])
    experts = graph.run(FIND_EXPERT, {"topic": rows[0]["topic"], "limit": 50})
    return _out("get_owner", GET_OWNER, p, rows, **build_owner_result(rows, experts))


def blast_radius(service: str):
    p = {"svc": service}
    return _out("blast_radius", BLAST_RADIUS, p, graph.run(BLAST_RADIUS, p))


def bus_factor():
    return _out("bus_factor", BUS_FACTOR, {}, graph.run(BUS_FACTOR))


def finish_stale(rows: list) -> list:
    for r in rows:
        r["reasons"] = (["superseded"] if r["superseded_by"] else []) + (["author inactive"] if r["inactive_authors"] else [])
    return rows


def stale_docs():
    return _out("stale_docs", STALE_DOCS, {}, finish_stale(graph.run(STALE_DOCS)))


def topics():
    return graph.run(TOPICS)


def services():
    return graph.run(SERVICES)


def all_decisions():
    return graph.run(ALL_DECISIONS)


def get_node(node_id: str):
    rows = graph.run(GET_NODE, {"id": node_id})
    if not rows:
        return None
    return {"id": node_id, "kind": rows[0]["kind"], "properties": rows[0]["node"],
            "outgoing": graph.run(NODE_OUT, {"id": node_id}), "incoming": graph.run(NODE_IN, {"id": node_id})}


def _to_graph(rows: list, nodes: dict | None = None) -> dict:
    nodes = nodes if nodes is not None else {}
    links = []
    for r in rows:
        nodes.setdefault(r["a_id"], {"id": r["a_id"], "kind": r["a_kind"], "label": r["a_label"]})
        if r.get("b_id"):
            nodes.setdefault(r["b_id"], {"id": r["b_id"], "kind": r["b_kind"], "label": r["b_label"]})
            links.append({"source": r["a_id"], "target": r["b_id"], "rel": r["rel"]})
    return {"nodes": list(nodes.values()), "links": links}


def overview():
    """Teams, services, projects and their OWNS / DEPENDS_ON edges: the default map."""
    return _to_graph(graph.run(OVERVIEW))


def subgraph(ids: list[str], expand: bool = True):
    """Nodes for an answer (ids), links among them, optionally plus 1-hop non-bulk neighbours."""
    ids = list(dict.fromkeys(ids))[:60]
    nodes = {r["a_id"]: {"id": r["a_id"], "kind": r["a_kind"], "label": r["a_label"]} for r in graph.run(SUBGRAPH_NODES, {"ids": ids})}
    rows = graph.run(SUBGRAPH_LINKS, {"ids": ids})
    if expand:
        rows += graph.run(SUBGRAPH_EXPAND, {"ids": ids})
    g = _to_graph(rows, nodes)
    seen, uniq = set(), []
    for l in g["links"]:
        k = (l["source"], l["target"], l["rel"])
        if k not in seen:
            seen.add(k)
            uniq.append(l)
    return {"nodes": g["nodes"], "links": uniq, "highlight": ids}


ALL_QUERIES = {"FIND_EXPERT": (FIND_EXPERT, {"topic": "payment-retries", "limit": 5}),
               "FIND_DECISIONS": (FIND_DECISIONS, {"kw": "postgres"}),
               "TRACE_DECISION": (TRACE_DECISION, {"id": "D-001"}),
               "GET_OWNER": (GET_OWNER, {"svc": "notifications"}),
               "BLAST_RADIUS": (BLAST_RADIUS, {"svc": "ledger"}),
               "BUS_FACTOR": (BUS_FACTOR, {}), "STALE_DOCS": (STALE_DOCS, {}), "TOPICS": (TOPICS, {}),
               "SERVICES": (SERVICES, {}), "ALL_DECISIONS": (ALL_DECISIONS, {}), "GET_NODE": (GET_NODE, {"id": "D-001"}),
               "NODE_OUT": (NODE_OUT, {"id": "D-001"}), "NODE_IN": (NODE_IN, {"id": "D-001"}), "OVERVIEW": (OVERVIEW, {}),
               "SUBGRAPH_NODES": (SUBGRAPH_NODES, {"ids": ["D-001", "svc-ledger"]}),
               "SUBGRAPH_LINKS": (SUBGRAPH_LINKS, {"ids": ["D-001", "svc-ledger"]}),
               "SUBGRAPH_EXPAND": (SUBGRAPH_EXPAND, {"ids": ["D-001", "svc-ledger"]})}
