"""OrgMind agent: question -> tool choice -> Cypher -> grounded answer.

Pipeline (PRD section 6):
  1. choose_tool(): LLM picks a tool as JSON (validated); falls back to the rule router.
  2. run_tool():   backend runs the Cypher (queries.py). The LLM never sees or writes Cypher.
  3. write_answer(): LLM writes the answer from the returned rows ONLY; a grounding check rejects
                     answers that cite ids not present in the rows, falling back to compose_answer().
Works with no LLM configured (rule router + template answers), so the demo can't be broken by rate limits.
"""
import json
import pathlib
import re

from . import llm, queries

CACHE_PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "answer_cache.json"

TOOLS = {
    "find_expert": {"desc": "Who knows most about a topic (people ranked by authored/participated evidence)", "args": ["topic"]},
    "trace_decision": {"desc": "Why a decision was made, its sources, and whether it is still current", "args": ["query"]},
    "get_owner": {"desc": "Which team owns a service, who is primary and who is the backup", "args": ["service"]},
    "blast_radius": {"desc": "Which services (and owning teams) break if a service goes down", "args": ["service"]},
    "bus_factor": {"desc": "Topics that only one person authored/understands", "args": []},
    "stale_docs": {"desc": "Documents that are superseded or whose author is inactive", "args": []},
}

DEMO_QUESTIONS = [
    "Who should I ask about payment retries?",
    "Why did we move to Postgres, and is that still the plan?",
    "What breaks if the ledger service goes down?",
    "Which topics only one person understands?",
    "Which docs are outdated?",
    "Who owns the notifications service and who is the backup?",
]

# ------------------------------------------------------------------ matching helpers
STOP = set("the a an of to in on for and or is are was were do does did we us our i you should who what which why how when "
           "that this still plan move moved moving about ask with from it its be been has have had can could would".split())


def _stem(w: str) -> str:
    w = w.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def tokens(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-zA-Z0-9]+", text)]


def _tok_eq(a: str, b: str) -> bool:
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))


def _name_score(name: str, qtoks: list[str]) -> tuple[int, int]:
    """(matched tokens, total tokens) of a hyphenated name against the question tokens."""
    nt = tokens(name.replace("-", " "))
    return sum(any(_tok_eq(n, q) for q in qtoks) for n in nt), len(nt)


def match_name(q: str, names: list[str], require_all: bool = False) -> str | None:
    qt = [t for t in tokens(q) if t not in STOP]
    best, best_key = None, (0, 0)
    ties = 0
    for n in names:
        m, total = _name_score(n, qt)
        if m == 0 or (require_all and m < total):
            continue
        key = (m, m / total)
        if key > best_key:
            best, best_key, ties = n, key, 0
        elif key == best_key:
            ties += 1
    return best if ties == 0 else (best if best_key[1] == 1 else None)


def normalize_question(q: str) -> str:
    return " ".join(tokens(q))


# ------------------------------------------------------------------ routing
def route_question(q: str, topics: list[dict], services: list[dict]) -> dict | None:
    low = q.lower()
    svc_names = [s["name"] for s in services]
    topic_names = [t["name"] for t in topics]
    svc = match_name(q, svc_names, require_all=True)
    if re.search(r"only one person|bus factor|single point of failure|one person (understands|knows)|only person|who is the only", low):
        return {"tool": "bus_factor", "args": {}}
    if re.search(r"outdated|out of date|stale|obsolete|still true|superseded docs?", low):
        return {"tool": "stale_docs", "args": {}}
    if svc and re.search(r"what breaks|goes? down|go down|blast radius|impact|downstream|depends? on|outage|fails?|failure", low):
        return {"tool": "blast_radius", "args": {"service": svc}}
    if svc and re.search(r"\bowns?\b|owner|owned|backup|back-up|on[- ]call|responsible|maintain", low):
        return {"tool": "get_owner", "args": {"service": svc}}
    if re.search(r"why did we|why do we|why are we|\bdecision|still the plan|reversed|decided|current plan|rationale", low):
        return {"tool": "trace_decision", "args": {"query": q}}
    if re.search(r"\bwho\b|expert|ask about|knows?\b|know about|go-to|point person", low):
        topic = match_name(q, topic_names)
        if not topic and svc:
            topic = next((s["topic"] for s in services if s["name"] == svc), None)
        if topic:
            return {"tool": "find_expert", "args": {"topic": topic}}
    return None


def choose_tool(q: str, topics: list[dict], services: list[dict]) -> tuple[dict | None, str]:
    """Returns (route, how) where how is 'llm' or 'rules'."""
    if llm.available():
        try:
            system = ("You route questions about a company to exactly one tool. Return ONLY JSON: "
                      '{"tool": <name>, "args": {...}}.\nTools:\n' + "\n".join(f"- {k}({', '.join(v['args'])}): {v['desc']}" for k, v in TOOLS.items())
                      + f"\nAllowed topics: {json.dumps([t['name'] for t in topics])}\nAllowed services: {json.dumps([s['name'] for s in services])}\n"
                      "For trace_decision pass the user's question as `query`. Use an allowed topic/service value exactly.")
            r = llm.complete_json(system, q)
            valid = _validate_route(r, topics, services, q)
            if valid:
                return valid, "llm"
        except Exception:
            pass
    return route_question(q, topics, services), "rules"


def _validate_route(r: dict, topics, services, q) -> dict | None:
    tool, args = r.get("tool"), r.get("args") or {}
    if tool not in TOOLS:
        return None
    if tool == "find_expert" and args.get("topic") in {t["name"] for t in topics}:
        return {"tool": tool, "args": {"topic": args["topic"]}}
    if tool in ("blast_radius", "get_owner") and args.get("service") in {s["name"] for s in services}:
        return {"tool": tool, "args": {"service": args["service"]}}
    if tool == "trace_decision":
        return {"tool": tool, "args": {"query": args.get("query") or q}}
    if tool in ("bus_factor", "stale_docs"):
        return {"tool": tool, "args": {}}
    return None


# ------------------------------------------------------------------ tools
def pick_decision(query: str, decisions: list[dict]) -> dict | None:
    """Best-matching decision for the question; on ties prefer the earliest (the origin of a chain)."""
    qt = {t for t in tokens(query) if t not in STOP and len(t) > 2}
    m = re.search(r"\bD-[A-Z0-9-]+\b", query)
    if m:
        return next((d for d in decisions if d["id"] == m.group(0)), None)
    scored = []
    for d in decisions:
        st = tokens(d["summary"])
        sc = sum(any(_tok_eq(q, s) for s in st) for q in qt)
        if sc:
            scored.append((-sc, d["date"], d))
    return sorted(scored, key=lambda x: (x[0], x[1]))[0][2] if scored else None


def run_tool(tool: str, args: dict) -> dict:
    if tool == "find_expert":
        return queries.find_expert(args["topic"])
    if tool == "get_owner":
        return queries.get_owner(args["service"])
    if tool == "blast_radius":
        return queries.blast_radius(args["service"])
    if tool == "bus_factor":
        return queries.bus_factor()
    if tool == "stale_docs":
        return queries.stale_docs()
    if tool == "trace_decision":
        start = pick_decision(args["query"], queries.all_decisions())
        if not start:
            return {"tool": tool, "cypher": queries.ALL_DECISIONS.strip(), "params": {}, "rows": [], "chain": []}
        chain, cur = [], start["id"]
        for _ in range(6):  # follow SUPERSEDES forward to the current decision
            res = queries.trace_decision(cur)
            if not res["rows"]:
                break
            chain.append(res)
            nxt = res["rows"][0]["superseded_by"]
            if not nxt:
                break
            cur = sorted(nxt)[-1]
        return {"tool": tool, "cypher": "\n\n".join(c["cypher"] for c in chain[:1]), "params": {"id": start["id"]},
                "rows": [c["rows"][0] for c in chain], "chain": [c["rows"][0] for c in chain]}
    raise ValueError(tool)


# ------------------------------------------------------------------ ids, sources, grounding
ID_RE = re.compile(r"\b(?:D|PER|DOC|TCK|MSG)-[A-Za-z0-9-]+\b")


def extract_ids(result: dict) -> list[str]:
    t, rows, ids = result["tool"], result["rows"], []
    if t == "find_expert":
        for r in rows:
            ids += [r["person_id"]] + list(r["sources"])
    elif t == "trace_decision":
        for r in rows:
            ids += [r["id"], r.get("made_by_id")] + [s["id"] for s in r["sources"] if s.get("id")]
            ids += list(r.get("affects_ids", [])) + list(r["superseded_by"]) + list(r["supersedes"])
    elif t == "get_owner":
        for r in rows:
            ids += [r["service_id"], r["team_id"]] + [m["id"] for m in r["members"]]
    elif t == "blast_radius":
        ids += [f"svc-{result['params']['svc']}"]
        for r in rows:
            ids += [r["service_id"], r["team_id"]]
    elif t == "bus_factor":
        for r in rows:
            ids += [r["topic"], r["author_id"]]
    elif t == "stale_docs":
        for r in rows:
            ids += [r["id"]] + list(r["superseded_by"])
    return list(dict.fromkeys(i for i in ids if i))


def sources_of(ids: list[str]) -> list[str]:
    return [i for i in ids if re.match(r"(DOC|TCK|MSG|D)-", i)]


def _strings(x, out: set):
    if isinstance(x, str):
        out.add(x)
    elif isinstance(x, dict):
        for v in x.values():
            _strings(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _strings(v, out)
    return out


def is_grounded(answer: str, result: dict) -> bool:
    """Every id the answer cites must appear somewhere in the returned rows."""
    known = _strings(result["rows"], set())
    return all(i in known or any(i in k for k in known) for i in ID_RE.findall(answer))


# ------------------------------------------------------------------ deterministic answers
def _names(rows, key="name"):
    return ", ".join(r[key] for r in rows)


def compose_answer(result: dict) -> str:
    t, rows = result["tool"], result["rows"]
    if not rows:
        return "The graph has no matching results for that."
    if t == "find_expert":
        top = rows[0]
        s = f"Ask {top['person']} ({top['role']}): {top['evidence']} artifacts about this topic, expertise score {top['score']}"
        s += ". Note: they are no longer active." if not top["active"] else "."
        if len(rows) > 1:
            s += " Next best: " + "; ".join(f"{r['person']} (score {r['score']}{', inactive' if not r['active'] else ''})" for r in rows[1:3]) + "."
        return s + f" Evidence includes {', '.join(top['sources'][:3])}."
    if t == "trace_decision":
        first, last = rows[0], rows[-1]
        s = f"{first['id']} ({first['date']}, by {first['made_by'] or 'unknown'}): {first['summary']}."
        srcs = [x for x in first["sources"] if x.get("id")]
        if srcs:
            s += " Decided in " + ", ".join(f"{x['id']}" for x in srcs[:3]) + "."
        if last["id"] != first["id"]:
            s += f" This is no longer current: it was superseded, and the latest decision is {last['id']} ({last['date']}): {last['summary']}."
            if len(rows) > 2:
                s += f" (chain: {' -> '.join(r['id'] for r in rows)})"
        else:
            s += " It is still the current decision (nothing supersedes it)."
        return s
    if t == "get_owner":
        r = result
        row = rows[0]
        s = f"{row['service']} is owned by the {row['team']} team."
        if r.get("primary"):
            s += f" Primary: {r['primary']['name']} (score {r['primary']['score']})."
        s += f" Backup: {r['backup']['name']} (score {r['backup']['score']})." if r.get("backup") else " There is no active backup."
        return s + (" Warnings: " + " ".join(w if w.endswith(".") else w + "." for w in r["warnings"]) if r.get("warnings") else "")
    if t == "blast_radius":
        svc = result["params"]["svc"]
        by = {}
        for r in rows:
            by.setdefault(r["hops"], []).append(f"{r['service']} ({r['team'] or 'no owner'})")
        parts = [f"{len(by[h])} at {h} hop{'s' if h > 1 else ''}: {', '.join(by[h])}" for h in sorted(by)]
        return f"If {svc} goes down, {len(rows)} services are affected. " + "; ".join(parts) + "."
    if t == "bus_factor":
        return f"{len(rows)} topics have a single author: " + "; ".join(
            f"{r['topic']} (only {r['only_author']}{', who is inactive' if not r['author_active'] else ''}, {r['artifacts']} artifacts)" for r in rows) + "."
    if t == "stale_docs":
        return f"{len(rows)} documents look stale: " + "; ".join(f"{r['id']} {r['title']} ({', '.join(r['reasons'])})" for r in rows) + "."
    return json.dumps(rows)[:500]


def write_answer(question: str, result: dict) -> tuple[str, str]:
    """(answer, how). LLM writes from rows only; falls back to the template if it fails or is ungrounded."""
    base = compose_answer(result)
    if not llm.available() or not result["rows"]:
        return base, "template"
    try:
        extra = {k: result[k] for k in ("primary", "backup", "warnings") if k in result}
        payload = json.dumps({"rows": result["rows"], **extra}, default=str)[:7000]
        text = llm.complete(
            "You answer questions about a company using ONLY the JSON data provided. Never use outside knowledge. "
            "Cite evidence by its id (e.g. D-002, DOC-005) in the sentence it supports. Be direct, under 120 words, no preamble. "
            "If the data says something is superseded or inactive, say so clearly.",
            f"Question: {question}\nData: {payload}").strip()
        if text and is_grounded(text, result):
            return text, "llm"
    except Exception:
        pass
    return base, "template"


# ------------------------------------------------------------------ cache (clears on live update)
_cache: dict = {}


def load_cache():
    if CACHE_PATH.exists():
        _cache.update(json.loads(CACHE_PATH.read_text()))


def cache_clear():
    _cache.clear()


def save_cache():
    CACHE_PATH.write_text(json.dumps(_cache, indent=1, default=str))


# ------------------------------------------------------------------ entry point
def ask(question: str, use_cache: bool = True) -> dict:
    key = normalize_question(question)
    if use_cache and key in _cache:
        return {**_cache[key], "cached": True}
    topics, services = queries.topics(), queries.services()
    route, routed_by = choose_tool(question, topics, services)
    if not route:
        return {"question": question, "answer": "I couldn't map that to a graph tool. Try asking who knows a topic, who owns a service, "
                "what breaks if a service goes down, why a decision was made, which topics have one expert, or which docs are outdated.",
                "tool": None, "args": {}, "cypher": "", "params": {}, "rows": [], "sources": [], "highlight": [], "cached": False,
                "routed_by": routed_by, "answered_by": "none"}
    result = run_tool(route["tool"], route["args"])
    answer, answered_by = write_answer(question, result)
    ids = extract_ids(result)
    out = {"question": question, "answer": answer, "tool": route["tool"], "args": route["args"], "cypher": result["cypher"],
           "params": result["params"], "rows": result["rows"], "chain": result.get("chain"), "sources": sources_of(ids), "highlight": ids,
           "routed_by": routed_by, "answered_by": answered_by, "cached": False}
    if "warnings" in result:
        out["warnings"] = result["warnings"]
    if use_cache:
        _cache[key] = out
    return out
