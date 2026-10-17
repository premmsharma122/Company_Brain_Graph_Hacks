"""Generate the fictional 'Acme Payments' dataset -> data/seed.json (deterministic).

Run:  python data/generate_data.py
Targets: 40 people, 6 teams, 12 services, 150 messages, 60 tickets, 25 documents.

Seeded stories (the demo depends on these):
  1. Ledger MySQL->Postgres decision (D-001) later rolled back (D-002 supersedes D-001)
  2. Two engineers left (Marcus Webb, Tom Fischer) -> stale docs + bus-factor risk
  3. Single-author topics: settlement-reconciliation, hsm-key-rotation, notification-templates
  4. Auth RFC v1 replaced by RFC v2 (document + decision supersede chains)
  5. Notifications: Kafka (D-007) replaced by SQS (D-008); tiny team with a weak backup
"""
import json
import random
import datetime as dt
import pathlib

rng = random.Random(42)
OUT = pathlib.Path(__file__).parent / "seed.json"


def D(s):
    return dt.date.fromisoformat(s)


FIRST = ["Aarav", "Bianca", "Chen", "Diego", "Elena", "Farid", "Grace", "Hiro", "Isla", "Jamal", "Kiran", "Lena", "Mateo", "Nia",
         "Omar", "Pooja", "Quinn", "Rafael", "Sofia", "Tariq", "Uma", "Victor", "Wen", "Ximena", "Yusuf", "Zara", "Arjun", "Beth",
         "Carlos", "Divya", "Ethan", "Fatima", "Gabriel", "Hana", "Ivan", "Julia", "Karan", "Leila", "Mohan", "Nadia"]
LAST = ["Patel", "Lindqvist", "Moreno", "Haddad", "Tanaka", "Brooks", "Silva", "Novak", "Kapoor", "Ahmed", "Costa", "Ibrahim",
        "Singh", "Larsen", "Reyes", "Khan", "Weber", "Ortiz", "Sato", "Dubois", "Mehta", "Cohen", "Rossi", "Nguyen", "Park", "Bauer",
        "Iyer", "Garcia", "Hughes", "Yilmaz", "Petrov", "Joshi", "Almeida", "Kim", "Roy", "Schmidt", "Verma", "Dasgupta", "Alvarez", "Berg"]

TEAMS = {  # key: (name, size)
    "payments": ("Payments Core", 8), "ledger": ("Ledger & Settlement", 7), "risk": ("Risk & Fraud", 7),
    "platform": ("Platform & Infra", 8), "notifications": ("Notifications", 3), "merchant": ("Merchant Experience", 7)}

# (name, tier, owning team, primary topic)
SERVICES = [
    ("payments-api", 1, "payments", "payment-routing"), ("retry-engine", 1, "payments", "payment-retries"),
    ("ledger", 1, "ledger", "ledger-schema"), ("settlement", 2, "ledger", "settlement-reconciliation"),
    ("fraud-engine", 1, "risk", "fraud-rules"), ("risk-scoring", 2, "risk", "risk-scoring"),
    ("auth-service", 1, "platform", "authentication"), ("api-gateway", 1, "platform", "rate-limiting"),
    ("notifications", 2, "notifications", "notification-queue"), ("email-sender", 3, "notifications", "notification-templates"),
    ("merchant-dashboard", 2, "merchant", "merchant-onboarding"), ("webhooks", 2, "merchant", "webhook-delivery")]
# (A, B) means A DEPENDS_ON B
DEPENDS = [("payments-api", "ledger"), ("payments-api", "auth-service"), ("payments-api", "fraud-engine"),
           ("payments-api", "retry-engine"), ("retry-engine", "ledger"), ("retry-engine", "notifications"),
           ("settlement", "ledger"), ("fraud-engine", "risk-scoring"), ("merchant-dashboard", "payments-api"),
           ("merchant-dashboard", "auth-service"), ("api-gateway", "auth-service"), ("api-gateway", "payments-api"),
           ("webhooks", "payments-api"), ("webhooks", "notifications"), ("notifications", "email-sender")]
PROJECTS = [("Postgres Migration", "paused", "ledger"), ("Auth v2 Rollout", "completed", "platform"),
            ("SQS Notification Queue", "active", "notifications"), ("Fraud Rules v3", "active", "risk")]
# (topic, team, service)
TOPICS = [
    ("payment-retries", "payments", "retry-engine"), ("idempotency", "payments", "payments-api"),
    ("payment-routing", "payments", "payments-api"), ("ledger-schema", "ledger", "ledger"),
    ("postgres-migration", "ledger", "ledger"), ("settlement-reconciliation", "ledger", "settlement"),
    ("fraud-rules", "risk", "fraud-engine"), ("risk-scoring", "risk", "risk-scoring"),
    ("chargebacks", "risk", "fraud-engine"), ("authentication", "platform", "auth-service"),
    ("rate-limiting", "platform", "api-gateway"), ("hsm-key-rotation", "platform", "auth-service"),
    ("incident-response", "platform", "api-gateway"), ("notification-queue", "notifications", "notifications"),
    ("notification-templates", "notifications", "email-sender"), ("email-deliverability", "notifications", "email-sender"),
    ("merchant-onboarding", "merchant", "merchant-dashboard"), ("webhook-delivery", "merchant", "webhooks"),
    ("dashboard-performance", "merchant", "merchant-dashboard"), ("reporting-exports", "merchant", "merchant-dashboard")]
TOPIC_TEAM = {t: tm for t, tm, _ in TOPICS}

# ------------------------------------------------------------------ people
SPECIAL = {"notifications": ["Priya Nair", "Marcus Webb", "Dev Malhotra"],
           "ledger": ["Anita Rao"], "platform": ["Sam Okafor", "Tom Fischer"]}
LEFT = {"Marcus Webb": "2026-03-31", "Tom Fischer": "2025-11-30"}  # engineers who left
people, by_team, used = [], {}, set()
for key, (tname, size) in TEAMS.items():
    names = list(SPECIAL.get(key, []))
    i = len(people)
    while len(names) < size:
        n = f"{FIRST[i % 40]} {LAST[(i * 7 + 3) % 40]}"
        i += 1
        if n not in used and n not in names:
            names.append(n)
    members = []
    for j, n in enumerate(names):
        used.add(n)
        p = {"id": f"PER-{len(people) + 1:03d}", "name": n, "team": key, "active": n not in LEFT,
             "role": "Engineering Manager" if j == 0 else rng.choice(["Software Engineer", "Senior Engineer", "SRE", "Staff Engineer"])}
        if n in LEFT:
            p["left"] = LEFT[n]
        people.append(p)
        members.append(p)
    by_team[key] = members
P = {p["name"]: p for p in people}


def left(p):
    return D(p["left"]) if "left" in p else D("2026-10-10")


# single-author topics: only this person AUTHORS artifacts about it (others may only participate)
SINGLE = {"settlement-reconciliation": by_team["ledger"][2]["name"], "hsm-key-rotation": "Sam Okafor",
          "notification-templates": "Marcus Webb"}
WEIGHTS = {"notifications": [5, 3, 1]}  # Priya does most of the work, Dev is the thin backup

# ------------------------------------------------------------------ helpers
nodes = {k: [] for k in ["Person", "Team", "Service", "Project", "Document", "Ticket", "Message", "Topic", "Decision"]}
edges = []
PREFIX = {"Document": "DOC", "Ticket": "TCK", "Message": "MSG"}
counters = {"Document": 0, "Ticket": 0, "Message": 0}


def E(t, a, b):
    edges.append({"type": t, "from": list(a), "to": list(b)})


def rdate(a, b):
    a = D(a) if isinstance(a, str) else a
    b = D(b) if isinstance(b, str) else b
    return (a + dt.timedelta(days=rng.randint(0, max(0, (b - a).days)))).isoformat()


def eligible(team_keys, date):
    out = []
    for k in team_keys:
        out += [p for p in by_team[k] if left(p) >= D(date)]
    return out


def add(label, topics, date, author=None, **props):
    """Create a Document/Ticket/Message plus AUTHORED, ABOUT and PARTICIPATED_IN edges."""
    primary = topics[0]
    team = TOPIC_TEAM[primary]
    if author is None:
        if primary in SINGLE:
            author = SINGLE[primary]
        else:
            pool = [p for p in by_team[team] if left(p) >= D(date)]
            w = WEIGHTS.get(team)
            w = [w[by_team[team].index(p)] for p in pool] if w else None
            author = rng.choices(pool, weights=w)[0]["name"]
    counters[label] += 1
    node = {"id": f"{PREFIX[label]}-{counters[label]:03d}", "date": date, **props}
    nodes[label].append(node)
    E("AUTHORED", ("Person", P[author]["id"]), (label, node["id"]))
    for t in topics:
        E("ABOUT", (label, node["id"]), ("Topic", t))
    if label != "Document":
        extra = [rng.choice(list(TEAMS))] if rng.random() < .25 else []
        pool = [p for p in eligible([team] + extra, date) if p["name"] != author]
        for p in rng.sample(pool, k=min(len(pool), rng.randint(1, 3))):
            E("PARTICIPATED_IN", ("Person", p["id"]), (label, node["id"]))
    return node["id"]


def SVC(n): return ("Service", f"svc-{n}")
def PRJ(n): return ("Project", "prj-" + n.lower().replace(" ", "-"))
def lead(team): return by_team[team][0]["name"]


# ------------------------------------------------------------------ static structure
for t, tm, svc in TOPICS:
    nodes["Topic"].append({"id": t, "name": t, "team": tm, "service": svc})
for k, (n, _) in TEAMS.items():
    nodes["Team"].append({"id": f"team-{k}", "name": n})
for p in people:
    nodes["Person"].append({"id": p["id"], "name": p["name"], "role": p["role"], "active": p["active"]})
    E("MEMBER_OF", ("Person", p["id"]), ("Team", f"team-{p['team']}"))
for n, tier, tm, topic in SERVICES:
    nodes["Service"].append({"id": f"svc-{n}", "name": n, "tier": tier, "topic": topic})
    E("OWNS", ("Team", f"team-{tm}"), SVC(n))
for a, b in DEPENDS:
    E("DEPENDS_ON", SVC(a), SVC(b))
for n, st, tm in PROJECTS:
    nodes["Project"].append({"id": PRJ(n)[1], "name": n, "status": st})
    E("OWNS", ("Team", f"team-{tm}"), PRJ(n))

# ------------------------------------------------------------------ story documents
def doc(topics, date, title, kind, status="current", author=None):
    return add("Document", topics, date, author=author, title=title, kind=kind, status=status)


d_pg = doc(["postgres-migration", "ledger-schema"], "2025-03-10", "RFC-012: Migrate Ledger from MySQL to Postgres", "rfc", "outdated", "Anita Rao")
d_rb = doc(["postgres-migration", "incident-response"], "2026-01-20", "Postmortem: Ledger Postgres migration rollback", "postmortem", "current", "Anita Rao")
d_a1 = doc(["authentication"], "2024-06-05", "Auth RFC v1: Session tokens for internal services", "rfc", "outdated", "Tom Fischer")
d_a2 = doc(["authentication", "rate-limiting"], "2026-02-12", "Auth RFC v2: OAuth2 with short-lived JWTs", "rfc", "current", "Sam Okafor")
d_rt = doc(["payment-retries", "idempotency"], "2025-08-04", "RFC-021: Payment retry policy (exponential backoff)", "rfc")
d_kf = doc(["notification-queue"], "2025-02-10", "Design: Kafka-backed notification pipeline", "rfc", "outdated", "Marcus Webb")
d_sqs = doc(["notification-queue"], "2026-05-06", "RFC-034: Move notifications to SQS", "rfc", "current", "Priya Nair")
d_tpl = doc(["notification-templates"], "2025-06-18", "Notes: Notification template engine internals", "notes", "current", "Marcus Webb")
d_fr = doc(["fraud-rules"], "2025-11-03", "Notes: Fraud vendor evaluation (build vs buy)", "notes")
d_st = doc(["settlement-reconciliation"], "2025-09-02", "Runbook: Nightly settlement batch and reconciliation", "notes")
d_hsm = doc(["hsm-key-rotation"], "2025-07-21", "Runbook: HSM key rotation", "notes", "current", "Sam Okafor")
E("SUPERSEDES", ("Document", d_a2), ("Document", d_a1))
E("SUPERSEDES", ("Document", d_sqs), ("Document", d_kf))
E("SUPERSEDES", ("Document", d_rb), ("Document", d_pg))

# ------------------------------------------------------------------ decisions
dec_n = [0]


def decide(summary, date, by, src, affects, supersedes=None):
    dec_n[0] += 1
    did = f"D-{dec_n[0]:03d}"
    nodes["Decision"].append({"id": did, "summary": summary, "date": date, "status": "current"})
    E("MADE_BY", ("Decision", did), ("Person", P[by]["id"]))
    for s in src:
        E("DECIDED_IN", ("Decision", did), s)
    for a in affects:
        E("AFFECTS", ("Decision", did), a)
    if supersedes:
        E("SUPERSEDES", ("Decision", did), ("Decision", supersedes))
        next(d for d in nodes["Decision"] if d["id"] == supersedes)["status"] = "superseded"
    return did


def dd(i): return ("Document", i)
def msg(topics, date, text, author=None): return ("Message", add("Message", topics, date, author=author, channel="#" + topics[0], text=text))
def tck(topics, date, title, status, author=None): return ("Ticket", add("Ticket", topics, date, author=author, title=title, status=status))


D001 = decide("Move the ledger database from MySQL to Postgres for better JSON and partitioning support", "2025-03-12", "Anita Rao",
              [dd(d_pg)], [SVC("ledger"), PRJ("Postgres Migration")])
D002 = decide("Roll back the Postgres migration; stay on MySQL 8 until at least Q3 2027 after cutover latency regressions", "2026-01-22",
              lead("platform"), [dd(d_rb), msg(["postgres-migration"], "2026-01-22", "Decision: we are rolling back the Postgres migration. Staying on MySQL 8 for the ledger.", "Anita Rao")],
              [SVC("ledger"), PRJ("Postgres Migration")], D001)
D003 = decide("Use session tokens for internal service authentication", "2024-06-06", "Tom Fischer", [dd(d_a1)], [SVC("auth-service")])
D004 = decide("Adopt OAuth2 with short-lived JWTs for all service-to-service auth", "2026-02-13", "Sam Okafor", [dd(d_a2)],
              [SVC("auth-service"), PRJ("Auth v2 Rollout")], D003)
D005 = decide("Retry failed payments with exponential backoff, max 5 attempts", "2025-08-05", lead("payments"), [dd(d_rt)], [SVC("retry-engine")])
D006 = decide("Require idempotency keys on all payment API writes", "2025-05-14", lead("payments"),
              [tck(["idempotency"], "2025-05-14", "Enforce idempotency keys on POST /payments", "closed")], [SVC("payments-api")])
D007_OLD = decide("Use Kafka for the notification pipeline", "2025-02-11", "Marcus Webb", [dd(d_kf)], [SVC("notifications")])
D007 = decide("Move the notification queue from Kafka to SQS to cut ops overhead", "2026-05-07", "Priya Nair", [dd(d_sqs)],
              [SVC("notifications"), PRJ("SQS Notification Queue")], D007_OLD)
D009 = decide("Keep fraud rules in-house instead of buying a vendor engine", "2025-11-04", lead("risk"), [dd(d_fr)],
              [SVC("fraud-engine"), PRJ("Fraud Rules v3")])
D010 = decide("Run settlement batch nightly at 02:00 UTC", "2025-09-03", SINGLE["settlement-reconciliation"], [dd(d_st)], [SVC("settlement")])
D011 = decide("Apply per-merchant rate limits at the API gateway", "2026-03-09", "Sam Okafor",
              [msg(["rate-limiting"], "2026-03-09", "Decision: per-merchant rate limits go live on the gateway next sprint.", "Sam Okafor")], [SVC("api-gateway")])
D012 = decide("Deprecate webhook v1 payloads by end of 2026", "2026-04-15", lead("merchant"),
              [tck(["webhook-delivery"], "2026-04-15", "Deprecate webhook v1 payload format", "in_progress")], [SVC("webhooks")])

# ------------------------------------------------------------------ filler: documents (25), tickets (60), messages (150)
KINDS = ["rfc", "notes", "postmortem"]
LABEL = {"rfc": "RFC", "notes": "Notes", "postmortem": "Postmortem"}
i = 0
while len(nodes["Document"]) < 25:
    t = TOPICS[i % len(TOPICS)][0]
    k = KINDS[i % 3]
    i += 1
    if t in SINGLE:
        continue
    doc([t], rdate("2025-01-15", "2026-09-30"), f"{LABEL[k]}: {t.replace('-', ' ').title()}", k)

TK = ["Investigate flaky {x} alerts", "Add metrics for {x}", "Refactor {x} module", "Fix timeout in {x}", "Document {x} behaviour",
      "Load test {x}", "Upgrade dependencies for {x}"]
MS = ["Anyone looked at {x} lately? Seeing odd behaviour.", "Heads up: changing how we handle {x} next week.", "Can someone review my PR on {x}?",
      "Postmortem action item for {x} is done.", "Question about {x}: who last touched this?", "Shipped the {x} fix to prod, watching dashboards.",
      "Planning {x} work for next sprint, thoughts?", "Reminder: {x} runbook needs a refresh."]
i = 0
while len(nodes["Ticket"]) < 60:
    t = TOPICS[(i * 3) % len(TOPICS)][0]
    i += 1
    tck([t], rdate("2025-01-15", "2026-10-01"), rng.choice(TK).format(x=t.replace("-", " ")), rng.choice(["open", "closed", "closed", "in_progress"]))
i = 0
while len(nodes["Message"]) < 150:
    t = TOPICS[(i * 7) % len(TOPICS)][0]
    i += 1
    msg([t], rdate("2025-01-15", "2026-10-10"), rng.choice(MS).format(x=t.replace("-", " ")))

tix = [t["id"] for t in nodes["Ticket"]]
for _ in range(10):  # acyclic: lower index blocks higher index
    a, b = sorted(rng.sample(range(len(tix)), 2))
    E("BLOCKS", ("Ticket", tix[a]), ("Ticket", tix[b]))

# Dev Malhotra: thin backup on notifications (a little evidence, not much)
dev = P["Dev Malhotra"]["id"]
for m in [m for m in nodes["Message"] if m["channel"] == "#notification-queue"][:2]:
    E("PARTICIPATED_IN", ("Person", dev), ("Message", m["id"]))

# ------------------------------------------------------------------ dedupe + write
seen, uniq = set(), []
for e in edges:
    k = (e["type"], tuple(e["from"]), tuple(e["to"]))
    if k not in seen:
        seen.add(k)
        uniq.append(e)
OUT.write_text(json.dumps({"nodes": nodes, "edges": uniq}, indent=1))
print({k: len(v) for k, v in nodes.items()}, "edges:", len(uniq), "->", OUT)
