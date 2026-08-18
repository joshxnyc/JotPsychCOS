"""OpenRouter client. Falls back to a deterministic stub when no key is set,
so the whole loop still runs (and is testable) with zero credentials."""
import json, os, urllib.request, urllib.error
from . import config

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

class LLMError(RuntimeError): pass

def available() -> bool:
    return bool(config.OPENROUTER_API_KEY)

def complete(system: str, user: str, *, model: str | None = None,
             temperature: float = 0.4, max_tokens: int = 1200,
             json_mode: bool = False) -> str:
    if not available():
        return _stub(system, user, json_mode)
    body = {
        "model": model or config.OPENROUTER_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                 "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/",
                 "X-Title": "jotpsych-machine"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise LLMError(f"{e.code}: {e.read()[:400]!r}") from e

def complete_json(system: str, user: str, **kw) -> dict:
    raw = complete(system, user, json_mode=True, **kw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        s, e = raw.find("{"), raw.rfind("}")
        if s >= 0 and e > s:
            return json.loads(raw[s:e + 1])
        raise

def _stub(system: str, user: str, json_mode: bool) -> str:
    """No key? Return something structurally valid so the pipeline is provable."""
    if json_mode:
        return json.dumps({"_stub": True, "verdict": "pass", "score": 3,
                           "reasons": ["LLM stub: no OPENROUTER_API_KEY set"]})
    return ("[LLM STUB - no OPENROUTER_API_KEY set]\n"
            "Subject: Placeholder\n\nThis is stub output so the loop runs end to end.")
