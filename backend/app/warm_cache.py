"""Pre-compute answers for the demo questions and save them to data/answer_cache.json
(protects the demo from free-tier LLM rate limits). Re-run after every reseed.
Usage (from backend/): python -m app.warm_cache"""
from . import agent

for q in agent.DEMO_QUESTIONS:
    r = agent.ask(q, use_cache=True)
    print(f"[{r['tool']}] ({r['routed_by']}/{r['answered_by']}) {q}\n   -> {r['answer'][:110]}")
agent.save_cache()
print("saved", agent.CACHE_PATH)
