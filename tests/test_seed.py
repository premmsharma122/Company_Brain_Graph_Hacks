"""No-DB tests: validate seed.json encodes every demo story, and the rule-based parser.
Run:  python tests/test_seed.py   (or pytest)"""
import json, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed.json"
if not SEED.exists():
    subprocess.check_call([sys.executable, str(ROOT / "data" / "generate_data.py")])
sys.path.insert(0, str(ROOT / "backend"))
data = json.loads(SEED.read_text()); N = data["nodes"]; E = data["edges"]
byid = lambda l: {n["id"]: n for n in N[l]}
edges = lambda t: [(e["from"][1], e["to"][1]) for e in E if e["type"] == t]


def test_counts():
    assert len(N["Person"]) == 40 and len(N["Team"]) == 6 and len(N["Service"]) == 12
    assert len(N["Message"]) == 150 and len(N["Ticket"]) == 60 and len(N["Document"]) == 25


def test_edges_resolve():
    ids = {l: {n["id"] for n in v} for l, v in N.items()}
    for e in E:
        assert e["from"][1] in ids[e["from"][0]] and e["to"][1] in ids[e["to"][0]], e


def test_postgres_reversed():
    d = byid("Decision")
    assert ("D-002", "D-001") in edges("SUPERSEDES") and d["D-001"]["status"] == "superseded" and d["D-002"]["status"] == "current"


def test_auth_rfc_replaced():
    docs = {n["title"]: n["id"] for n in N["Document"]}
    assert (docs["Auth RFC v2: OAuth2 with short-lived JWTs"], docs["Auth RFC v1: Session tokens for internal services"]) in edges("SUPERSEDES")


def test_engineers_left():
    assert {p["name"] for p in N["Person"] if not p["active"]} == {"Marcus Webb", "Tom Fischer"}


def test_bus_factor_topics():
    people = byid("Person"); author_of = {}
    topics_of = {}
    for a, b in edges("ABOUT"): topics_of.setdefault(a, []).append(b)
    for p, x in edges("AUTHORED"):
        for t in topics_of.get(x, []): author_of.setdefault(t, set()).add(p)
    single = {t for t, s in author_of.items() if len(s) == 1}
    assert {"settlement-reconciliation", "hsm-key-rotation", "notification-templates"} <= single
    assert len(single) <= 6, single  # a handful, not everything


def test_blast_radius_ledger():
    dep = {}
    for a, b in edges("DEPENDS_ON"): dep.setdefault(b, set()).add(a)
    seen, frontier = set(), {"svc-ledger"}
    for _ in range(3):
        frontier = {x for s in frontier for x in dep.get(s, set())} - seen; seen |= frontier
    assert {"svc-payments-api", "svc-retry-engine", "svc-settlement", "svc-webhooks", "svc-api-gateway"} <= seen


def test_notifications_thin_backup():
    team = {p for p, t in edges("MEMBER_OF") if t == "team-notifications"}
    assert len(team) == 3


def test_parser():
    from app.ingest import parse_message
    topics = ["notification-queue", "payment-retries"]
    p = parse_message("Decision: we are reversing D-007. Going back to Kafka for the notification queue.", topics)
    assert p.is_decision and p.reverses == ["D-007"] and p.topics == ["notification-queue"]
    q = parse_message("Anyone looked at payment retries lately?", topics)
    assert not q.is_decision and q.topics == ["payment-retries"]


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns: f(); print("PASS", f.__name__)
