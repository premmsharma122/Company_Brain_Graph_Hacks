"""Run every core query against the live DB and report errors / row counts.
Usage (from backend/): python -m app.verify_queries
This is the 'test every query in FalkorDB' step from the PRD risk list."""
from . import graph, queries

ok = True
for name, (q, params) in queries.ALL_QUERIES.items():
    try:
        rows = graph.run(q, params)
        print(f"OK    {name:15s} rows={len(rows)}")
    except Exception as e:
        ok = False
        print(f"FAIL  {name:15s} {e}")
raise SystemExit(0 if ok else 1)
