"""FastAPI app. Every analytic endpoint returns the rows AND the Cypher used."""
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import agent, graph, ingest, llm, queries

app = FastAPI(title="OrgMind API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_methods=["*"], allow_headers=["*"])


agent.load_cache()


class ChatIn(BaseModel):
    question: str
    use_cache: bool = True


class IngestIn(BaseModel):
    text: str
    author: str
    channel: str = "#live"


@app.get("/health")
def health():
    try:
        n = graph.run("MATCH (n) RETURN count(n) AS nodes")[0]["nodes"]
        return {"status": "ok", "nodes": n, "llm": llm.provider()}
    except Exception as e:
        raise HTTPException(503, f"FalkorDB unreachable: {e}")


@app.get("/api/topics")
def topics(): return queries.topics()

@app.get("/api/expert")
def expert(topic: str, limit: int = 5): return queries.find_expert(topic, limit)

@app.get("/api/decisions")
def decisions(q: str): return queries.find_decisions(q)

@app.get("/api/decision/{decision_id}")
def decision(decision_id: str):
    out = queries.trace_decision(decision_id)
    if not out["rows"]:
        raise HTTPException(404, "Decision not found")
    return out

@app.get("/api/owner")
def owner(service: str):
    out = queries.get_owner(service)
    if not out["rows"]:
        raise HTTPException(404, "Service not found")
    return out

@app.get("/api/blast-radius")
def blast(service: str): return queries.blast_radius(service)

@app.get("/api/bus-factor")
def bus(): return queries.bus_factor()

@app.get("/api/stale-docs")
def stale(): return queries.stale_docs()

@app.post("/api/chat")
def chat(body: ChatIn):
    try:
        return agent.ask(body.question, body.use_cache)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")

@app.get("/api/demo-questions")
def demo_questions(): return agent.DEMO_QUESTIONS

@app.get("/api/graph/overview")
def graph_overview(): return queries.overview()

@app.get("/api/subgraph")
def subgraph(ids: str, expand: bool = True):
    return queries.subgraph([i for i in ids.split(",") if i], expand)

@app.get("/api/node/{node_id}")
def node(node_id: str):
    out = queries.get_node(node_id)
    if not out:
        raise HTTPException(404, "Node not found")
    return out

@app.get("/api/people")
def people(): return graph.run("MATCH (p:Person) RETURN p.id AS id, p.name AS name, p.active AS active ORDER BY p.name")

@app.post("/api/ingest")
def ingest_endpoint(body: IngestIn):
    try:
        out = ingest.ingest_message(body.text, body.author, body.channel)
        agent.cache_clear()  # the graph changed: cached answers are stale
        return out
    except ValueError as e:
        raise HTTPException(400, str(e))
