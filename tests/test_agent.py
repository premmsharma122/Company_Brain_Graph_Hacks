"""Agent tests with no DB and no LLM: routing, tool results (via fake_queries), answers, grounding, cache.
Run: python tests/test_agent.py   (or pytest)"""
import os, sys, pathlib
os.environ["LLM_PROVIDER"] = "none"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fake_queries
from app import agent
agent.queries = fake_queries          # swap the DB layer for the in-memory mirror
agent.CACHE_PATH = pathlib.Path("/tmp/orgmind_test_cache.json")
ask = lambda q: agent.ask(q, use_cache=False)


def test_routing_all_demo_questions():
    exp = ["find_expert", "trace_decision", "blast_radius", "bus_factor", "stale_docs", "get_owner"]
    for q, t in zip(agent.DEMO_QUESTIONS, exp):
        r = agent.route_question(q, fake_queries.topics(), fake_queries.services())
        assert r and r["tool"] == t, (q, r)


def test_arg_matching():
    T, S = fake_queries.topics(), fake_queries.services()
    assert agent.route_question("Who should I ask about payment retries?", T, S)["args"] == {"topic": "payment-retries"}
    assert agent.route_question("What breaks if the ledger service goes down?", T, S)["args"] == {"service": "ledger"}
    assert agent.route_question("Who owns the notifications service and who is the backup?", T, S)["args"] == {"service": "notifications"}
    assert agent.route_question("who knows about auth?", T, S)["args"] == {"topic": "authentication"}


def test_expert():
    r = ask("Who should I ask about payment retries?")
    assert r["rows"][0]["person"] == "Diego Park" and r["rows"][0]["score"] == 15, r["rows"][:2]
    assert "Diego Park" in r["answer"] and r["cypher"] and r["highlight"]


def test_postgres_decision_reversed():
    r = ask("Why did we move to Postgres, and is that still the plan?")
    assert [x["id"] for x in r["chain"]] == ["D-001", "D-002"], r["chain"]
    assert "no longer current" in r["answer"] and "D-002" in r["answer"] and "DOC-001" in r["answer"]
    assert "DOC-001" in r["sources"] and "D-002" in r["sources"]


def test_blast_radius():
    r = ask("What breaks if the ledger service goes down?")
    hop = {x["service"]: x["hops"] for x in r["rows"]}
    assert hop["payments-api"] == hop["retry-engine"] == hop["settlement"] == 1
    assert hop["webhooks"] == hop["api-gateway"] == hop["merchant-dashboard"] == 2
    assert "svc-ledger" in r["highlight"]


def test_bus_factor_and_stale():
    r = ask("Which topics only one person understands?")
    assert {x["topic"] for x in r["rows"]} == {"settlement-reconciliation", "hsm-key-rotation", "notification-templates"}
    assert "inactive" in r["answer"]
    s = ask("Which docs are outdated?")
    titles = " ".join(x["title"] for x in s["rows"])
    assert "Auth RFC v1" in titles and "Kafka" in titles and "template engine" in titles and "RFC-012" in titles


def test_owner_and_backup():
    r = ask("Who owns the notifications service and who is the backup?")
    assert r["rows"][0]["team"] == "Notifications"
    assert "Dev Malhotra" in r["answer"] and "Priya Nair" in r["answer"] and r["warnings"], r["answer"]


def test_live_update_target_is_d008():
    d = {x["id"]: x for x in fake_queries.all_decisions()}
    assert "SQS" in d["D-008"]["summary"] and d["D-008"]["status"] == "current" and d["D-007"]["status"] == "superseded"
    r = ask("Why did we move notifications to SQS, and is that still the plan?")
    assert r["chain"][0]["id"] == "D-008" and "still the current decision" in r["answer"]


def test_unroutable():
    r = ask("What's the weather like?")
    assert r["tool"] is None and "couldn't map" in r["answer"]


def test_grounding_check():
    r = ask("Which docs are outdated?")
    assert not agent.is_grounded("This was decided in D-999.", ask("Why did we move to Postgres?"))


def test_cache_roundtrip_and_clear():
    a = agent.ask("Which docs are outdated?"); b = agent.ask("which docs are OUTDATED")
    assert not a["cached"] and b["cached"]
    agent.cache_clear(); assert not agent.ask("Which docs are outdated?")["cached"]
    agent.cache_clear()


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("PASS", k)
