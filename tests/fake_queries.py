"""In-memory stand-in for app.queries, computed from data/seed.json with plain Python.
Mirrors the SHAPE of every real wrapper's result so agent.py can be tested end to end with no database.
It does NOT prove the Cypher is valid FalkorDB syntax: that is what `python -m app.verify_queries` is for."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import queries as real  # constants + pure helpers only

data = json.loads((ROOT / "data" / "seed.json").read_text())
N, E = data["nodes"], data["edges"]
ALL = {n["id"]: {**n, "_kind": k} for k, v in N.items() for n in v}
ALL_DECISIONS, TRACE_DECISION = real.ALL_DECISIONS, real.TRACE_DECISION


def out(tool, cypher, params, rows, **extra): return {"tool": tool, "cypher": cypher.strip(), "params": params, "rows": rows, **extra}
def edges(t): return [(e["from"][1], e["to"][1]) for e in E if e["type"] == t]
def label(n): return n.get("title") or n.get("text")
topics_of = {}
for a, b in edges("ABOUT"): topics_of.setdefault(a, []).append(b)


def topics(): return sorted(({"name": t["name"], "service": t["service"]} for t in N["Topic"]), key=lambda x: x["name"])
def services(): return sorted(({"id": s["id"], "name": s["name"], "topic": s["topic"]} for s in N["Service"]), key=lambda x: x["name"])
def all_decisions(): return sorted(({k: d[k] for k in ("id", "summary", "date", "status")} for d in N["Decision"]), key=lambda d: d["date"])


def find_expert(topic, limit=5):
    sc, ev = {}, {}
    for t in ("AUTHORED", "PARTICIPATED_IN"):
        for p, x in edges(t):
            if p in ALL and ALL[p]["_kind"] == "Person" and topic in topics_of.get(x, []):
                sc[p] = sc.get(p, 0) + (2 if t == "AUTHORED" else 1); ev.setdefault(p, []).append(x)
    rows = [{"person_id": p, "person": ALL[p]["name"], "role": ALL[p]["role"], "active": ALL[p]["active"], "score": s,
             "evidence": len(set(ev[p])), "sources": list(dict.fromkeys(ev[p]))[:5]} for p, s in sc.items()]
    return out("find_expert", real.FIND_EXPERT, {"topic": topic, "limit": limit}, sorted(rows, key=lambda r: -r["score"])[:limit])


def find_decisions(kw): return out("find_decisions", real.FIND_DECISIONS, {"kw": kw}, [d for d in all_decisions() if kw.lower() in d["summary"].lower()])


def trace_decision(did):
    d = ALL.get(did)
    if not d: return out("trace_decision", real.TRACE_DECISION, {"id": did}, [])
    out_e = lambda t: [b for a, b in edges(t) if a == did]
    sup = edges("SUPERSEDES")
    made = (out_e("MADE_BY") or [None])[0]
    srcs = [{"id": s, "kind": ALL[s]["_kind"], "label": label(ALL[s])} for s in out_e("DECIDED_IN")]
    row = {"id": did, "summary": d["summary"], "date": d["date"], "status": d["status"], "made_by": ALL[made]["name"] if made else None,
           "made_by_id": made, "is_current": not any(b == did for a, b in sup if a in ALL and ALL[a]["_kind"] == "Decision"), "sources": srcs,
           "superseded_by": [a for a, b in sup if b == did and ALL[a]["_kind"] == "Decision"],
           "supersedes": [b for a, b in sup if a == did and ALL[b]["_kind"] == "Decision"],
           "affects": [ALL[a]["name"] for a in out_e("AFFECTS")], "affects_ids": out_e("AFFECTS")}
    return out("trace_decision", real.TRACE_DECISION, {"id": did}, [row])


def get_owner(service):
    s = next((x for x in N["Service"] if x["name"] == service), None)
    if not s: return out("get_owner", real.GET_OWNER, {"svc": service}, [])
    team = next(a for a, b in edges("OWNS") if b == s["id"])
    members = [{"id": p, "name": ALL[p]["name"], "role": ALL[p]["role"], "active": ALL[p]["active"]} for p, t in edges("MEMBER_OF") if t == team]
    rows = [{"service_id": s["id"], "service": service, "tier": s["tier"], "topic": s["topic"], "team_id": team, "team": ALL[team]["name"], "members": members}]
    return out("get_owner", real.GET_OWNER, {"svc": service}, rows, **real.build_owner_result(rows, find_expert(s["topic"], 50)["rows"]))


def blast_radius(service):
    sid = f"svc-{service}"; deps = {}
    for a, b in edges("DEPENDS_ON"): deps.setdefault(b, []).append(a)
    seen, frontier, hops = {}, [sid], 0
    while frontier and hops < 3:
        hops += 1; nxt = []
        for s in frontier:
            for d in deps.get(s, []):
                if d not in seen: seen[d] = hops; nxt.append(d)
        frontier = nxt
    own = {b: a for a, b in edges("OWNS")}
    rows = [{"service_id": d, "service": ALL[d]["name"], "tier": ALL[d]["tier"], "team_id": own.get(d), "team": ALL[own[d]]["name"] if d in own else None, "hops": h} for d, h in seen.items()]
    return out("blast_radius", real.BLAST_RADIUS, {"svc": service}, sorted(rows, key=lambda r: (r["hops"], r["service"])))


def bus_factor():
    au = {}
    for p, x in edges("AUTHORED"):
        if p in ALL and ALL[p]["_kind"] == "Person":
            for t in topics_of.get(x, []): au.setdefault(t, {}).setdefault(p, 0); au[t][p] += 1
    rows = [{"topic": t, "only_author": ALL[list(a)[0]]["name"], "author_id": list(a)[0], "author_active": ALL[list(a)[0]]["active"], "artifacts": sum(a.values())} for t, a in au.items() if len(a) == 1]
    return out("bus_factor", real.BUS_FACTOR, {}, sorted(rows, key=lambda r: -r["artifacts"]))


def stale_docs():
    newer = {}
    for a, b in edges("SUPERSEDES"):
        if ALL[a]["_kind"] == "Document": newer.setdefault(b, []).append(a)
    inactive = {}
    for p, x in edges("AUTHORED"):
        if p in ALL and ALL[p]["_kind"] == "Person" and not ALL[p]["active"]: inactive.setdefault(x, []).append(ALL[p]["name"])
    rows = [{"id": d["id"], "title": d["title"], "date": d["date"], "superseded_by": newer.get(d["id"], []), "inactive_authors": inactive.get(d["id"], [])}
            for d in sorted(N["Document"], key=lambda d: d["date"]) if d["id"] in newer or d["id"] in inactive]
    return out("stale_docs", real.STALE_DOCS, {}, real.finish_stale(rows))
