"""Live-update ingest (rule-based fallback parser).

parse_message() is pure (no DB) so it is unit-testable. ingest_message() writes with MERGE,
so re-running the same message is safe.

parse_smart() tries the LLM extractor first (llm.extract_message) and falls back to parse_message()
when the LLM is unconfigured, fails, or is rate-limited. Rule-based reversal ids are always unioned in,
so "reversing D-007" can never be missed because of a flaky LLM.
"""
import re
import time
import datetime as dt
from dataclasses import dataclass, field

from . import graph

DECISION_RE = re.compile(r"\b(we (have )?decided|decision:|we(?:'re| are) going with|going with|switching to|moving to|reverting|reversing|rolling back|roll back)\b", re.I)
REVERSE_RE = re.compile(r"\b(revers\w*|revert\w*|overturn\w*|roll(?:ing)? back|supersed\w*|cancel\w*|undo\w*)\b", re.I)
DEC_ID_RE = re.compile(r"\bD-\d{3}\b")


@dataclass
class Parsed:
    topics: list[str] = field(default_factory=list)
    is_decision: bool = False
    reverses: list[str] = field(default_factory=list)
    summary: str = ""


def parse_message(text: str, known_topics: list[str]) -> Parsed:
    low = text.lower()
    topics = [t for t in known_topics if t in low or t.replace("-", " ") in low]
    ids = DEC_ID_RE.findall(text)
    reversal = bool(REVERSE_RE.search(text)) and bool(ids)
    is_decision = bool(DECISION_RE.search(text)) or reversal
    first = re.split(r"(?<=[.!?])\s", text.strip())[0]
    return Parsed(topics=topics, is_decision=is_decision, reverses=ids if reversal else [], summary=first[:240])


def parse_smart(text: str, known_topics: list[str]) -> tuple[Parsed, str]:
    rules = parse_message(text, known_topics)
    try:
        from . import llm
        if not llm.available():
            return rules, "rules"
        r = llm.extract_message(text, known_topics)
        topics = [t for t in r.get("topics", []) if t in known_topics] or rules.topics
        reverses = list(dict.fromkeys([x for x in r.get("reverses", []) if DEC_ID_RE.fullmatch(str(x))] + rules.reverses))
        is_dec = bool(r.get("is_decision")) or rules.is_decision or bool(reverses)
        return Parsed(topics=topics, is_decision=is_dec, reverses=reverses, summary=(r.get("summary") or rules.summary)[:240]), "llm"
    except Exception:
        return rules, "rules"


def ingest_message(text: str, author: str, channel: str = "#live", date: str | None = None) -> dict:
    date = date or dt.date.today().isoformat()
    stamp = int(time.time())
    person = graph.run("MATCH (p:Person) WHERE p.id = $a OR toLower(p.name) = toLower($a) RETURN p.id AS id, p.name AS name LIMIT 1", {"a": author})
    if not person:
        raise ValueError(f"Unknown author: {author}")
    pid = person[0]["id"]
    known = [t["name"] for t in graph.run("MATCH (t:Topic) RETURN t.name AS name")]
    parsed, method = parse_smart(text, known)

    mid = f"MSG-LIVE-{stamp}"
    graph.run("MATCH (p:Person {id: $pid}) MERGE (m:Message {id: $mid}) SET m.channel = $ch, m.text = $text, m.date = $date "
              "MERGE (p)-[:AUTHORED]->(m)", {"pid": pid, "mid": mid, "ch": channel, "text": text, "date": date})
    for t in parsed.topics:
        graph.run("MATCH (m:Message {id: $mid}) MATCH (t:Topic {name: $t}) MERGE (m)-[:ABOUT]->(t)", {"mid": mid, "t": t})

    touched = {"messages": [mid], "topics": parsed.topics, "decisions": [], "superseded": [], "services": []}
    result = {"message_id": mid, "parsed": parsed.__dict__, "parsed_by": method, "touched": touched, "notes": []}
    if not parsed.is_decision:
        return result

    did = f"D-LIVE-{stamp}"
    graph.run("MATCH (m:Message {id: $mid}) MATCH (p:Person {id: $pid}) "
              "MERGE (d:Decision {id: $did}) SET d.summary = $s, d.date = $date, d.status = 'current' "
              "MERGE (d)-[:DECIDED_IN]->(m) MERGE (d)-[:MADE_BY]->(p)", {"mid": mid, "pid": pid, "did": did, "s": parsed.summary, "date": date})
    touched["decisions"].append(did)
    for t in parsed.topics:
        for r in graph.run("MATCH (t:Topic {name: $t}) RETURN t.service AS svc", {"t": t}):
            if r["svc"]:
                graph.run("MATCH (d:Decision {id: $did}) MATCH (s:Service {name: $svc}) MERGE (d)-[:AFFECTS]->(s)", {"did": did, "svc": r["svc"]})
                touched["services"].append(r["svc"])
    for old in parsed.reverses:
        if not graph.run("MATCH (o:Decision {id: $old}) RETURN o.id AS id", {"old": old}):
            result["notes"].append(f"{old} not found, skipped")
            continue
        graph.run("MATCH (d:Decision {id: $new}) MATCH (o:Decision {id: $old}) MERGE (d)-[:SUPERSEDES]->(o) SET o.status = 'superseded'", {"new": did, "old": old})
        graph.run("MATCH (o:Decision {id: $old})-[:AFFECTS]->(a) MATCH (d:Decision {id: $new}) MERGE (d)-[:AFFECTS]->(a)", {"new": did, "old": old})
        touched["superseded"].append(old)
    return result
