"""Thin LLM wrapper (Gemini or Groq, both free tier). Everything here is optional: callers must
handle `None` / exceptions and fall back to the rule-based paths.

Env: LLM_PROVIDER = gemini | groq | none (default: auto = gemini if GEMINI_API_KEY else groq if GROQ_API_KEY).
     GEMINI_MODEL, GROQ_MODEL override the default model names (check current free-tier model names).
"""
import json
import os
import re

from dotenv import load_dotenv

load_dotenv()


def provider() -> str:
    p = os.getenv("LLM_PROVIDER", "auto").lower()
    if p == "none":
        return "none"
    if p in ("gemini", "groq"):
        return p if os.getenv(f"{p.upper()}_API_KEY") else "none"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    return "none"


def available() -> bool:
    return provider() != "none"


def complete(system: str, user: str, json_mode: bool = False) -> str:
    p = provider()
    if p == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"), system_instruction=system)
        cfg = {"temperature": 0}
        if json_mode:
            cfg["response_mime_type"] = "application/json"
        return model.generate_content(user, generation_config=cfg).text
    if p == "groq":
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        r = client.chat.completions.create(model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), temperature=0,
                                           messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **kwargs)
        return r.choices[0].message.content
    raise RuntimeError("No LLM configured")


def complete_json(system: str, user: str) -> dict:
    text = complete(system, user, json_mode=True).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def extract_message(text: str, known_topics: list[str]) -> dict:
    """LLM extraction for live updates -> {topics, is_decision, reverses, summary}."""
    system = ("You extract structured facts from one company chat message. Return ONLY JSON with keys: "
              "topics (array, chosen ONLY from the allowed list), is_decision (bool: a decision is announced or reversed), "
              "reverses (array of decision ids like D-007 that this message reverses/overturns/replaces, else []), "
              "summary (<=200 chars, the decision stated as a plain sentence, else '').")
    return complete_json(system, f"Allowed topics: {json.dumps(known_topics)}\nMessage: {text}")
