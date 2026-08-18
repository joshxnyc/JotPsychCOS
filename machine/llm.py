"""OpenRouter client. Falls back to a deterministic stub when no key is set,
so the whole loop still runs (and is testable) with zero credentials."""
import json, os, re, urllib.request, urllib.error
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
                 "User-Agent": config.USER_AGENT,
                 "HTTP-Referer": "https://github.com/",
                 "X-Title": "jotpsych-machine"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise LLMError(f"{e.code}: {e.read()[:400]!r}") from e

def extract_json(raw: str) -> dict:
    """Pull an object out of whatever the model actually returned.

    Handles a bare object, a ```json fence, and prose wrapped around one.
    Raises LLMError (never JSONDecodeError) so callers have one thing to catch.
    """
    text = (raw or "").strip()
    if not text:
        raise LLMError("model returned empty content")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Scan for the first balanced {...}, ignoring braces inside strings.
    start = text.find("{")
    if start >= 0:
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(text[start:], start):
            if in_str:
                if esc:            esc = False
                elif ch == "\\":   esc = True
                elif ch == '"':    in_str = False
            elif ch == '"':        in_str = True
            elif ch == "{":        depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise LLMError(f"no JSON object in model output: {text[:300]!r}")

def complete_json(system: str, user: str, *, max_tokens: int = 1200, **kw) -> dict:
    """Structured output that does not depend on the provider honouring
    response_format. Tries JSON mode, then falls back to asking plainly.

    A JSON-mode request that comes back empty is the common failure: some
    providers spend the whole token budget before emitting content. The retry
    drops response_format and states the requirement in the prompt instead.
    """
    attempts = []
    for json_mode, sys_suffix in ((True, ""),
                                  (False, "\n\nReturn ONLY a single JSON object. "
                                          "No prose, no markdown fence, no explanation.")):
        try:
            raw = complete(system + sys_suffix, user, json_mode=json_mode,
                           max_tokens=max_tokens, **kw)
            return extract_json(raw)
        except LLMError as e:
            attempts.append(f"json_mode={json_mode}: {e}")
    raise LLMError("could not obtain JSON from the model — " + " | ".join(attempts))

def _stub(system: str, user: str, json_mode: bool) -> str:
    """No key? Return something structurally valid, so the whole loop is
    provable by anyone who clones the repo without credentials.

    The stub is shaped by what the caller asked for. A draft request gets a
    real, on-brand, QC-passing message; a judge request gets a verdict. Both
    are labeled as stub output in the payload."""
    if not json_mode:
        return "[LLM STUB - no OPENROUTER_API_KEY set]"
    if '"subject"' in system:
        return json.dumps({
            "_stub": True,
            "subject": "Running JotPsych beside what you already use",
            "body": (
                "You looked at JotPsych a while back and stayed where you were. "
                "That is usually the right call mid-contract.\n\n"
                "Worth knowing: you do not have to move anything. JotPsych runs "
                "alongside the system you are on today, and it takes about five "
                "minutes to set up. Notes and claims get checked against payer "
                "rules before they go out, which is where most denials start.\n\n"
                "If it is useful later, it will still be here.\n\n"
                "— Josh, JotPsych"),
            "claims": [
                "JotPsych runs alongside an existing EHR",
                "setup takes about five minutes",
                "notes and claims are checked against payer rules"]})
    return json.dumps({"_stub": True, "verdict": "pass", "score": 3,
                       "reasons": ["LLM stub: no OPENROUTER_API_KEY set"]})
