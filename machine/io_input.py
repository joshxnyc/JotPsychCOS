"""INPUT. Reads things the machine did not write.

Two sources, both real:
  1. CSV files dropped in inbox/  (replace these with the client's own list)
  2. NPPES  - the free federal NPI registry API. Live, public, no key.
     https://npiregistry.cms.hhs.gov/api-page
"""
import csv, io, json, hashlib, os, urllib.parse, urllib.request
from . import config

NPPES = "https://npiregistry.cms.hhs.gov/api/"

def read_csv(name: str) -> list[dict]:
    """Read any CSV dropped in inbox/. Returns list of dicts with a stable id."""
    path = config.INBOX / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k}
                for r in csv.DictReader(f)]
    for r in rows:
        r.setdefault("id", _rid(r))
    return rows

def _rid(row: dict) -> str:
    key = (row.get("npi") or row.get("email") or json.dumps(row, sort_keys=True))
    return hashlib.sha1(key.encode()).hexdigest()[:12]

def nppes_lookup(*, npi: str = "", first: str = "", last: str = "",
                 state: str = "", taxonomy: str = "", limit: int = 5) -> list[dict]:
    """Live call to the federal NPI registry. Returns normalised clinician records."""
    params = {"version": "2.1", "limit": str(limit)}
    if npi:      params["number"] = npi
    if first:    params["first_name"] = first
    if last:     params["last_name"] = last
    if state:    params["state"] = state
    if taxonomy: params["taxonomy_description"] = taxonomy
    url = NPPES + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as e:
        return [{"_error": str(e)}]
    return [_norm(x) for x in data.get("results", [])]

def _norm(rec: dict) -> dict:
    basic = rec.get("basic", {}) or {}
    tax   = (rec.get("taxonomies") or [{}])
    primary = next((t for t in tax if t.get("primary")), tax[0] if tax else {})
    loc = next((a for a in rec.get("addresses", []) if a.get("address_purpose") == "LOCATION"),
               (rec.get("addresses") or [{}])[0])
    return {
        "npi": rec.get("number"),
        "entity": rec.get("enumeration_type"),
        "name": " ".join(filter(None, [basic.get("first_name"), basic.get("last_name")]))
                or basic.get("organization_name", ""),
        "credential": basic.get("credential", ""),
        "taxonomy": primary.get("desc", ""),
        "specialty_code": primary.get("code", ""),
        "state": loc.get("state", ""),
        "city": loc.get("city", ""),
        "phone": loc.get("telephone_number", ""),
        "address_1": loc.get("address_1", ""),
        "postal_code": (loc.get("postal_code", "") or "")[:5],
        "enumerated": basic.get("enumeration_date", ""),
        # CMS's own change stamp. Independent of our diff, so a change we do not
        # model still leaves a trace.
        "last_updated": basic.get("last_updated", ""),
        "source": "NPPES",
    }

def enrich(rows: list[dict]) -> list[dict]:
    """Attach live registry facts to each inbox row. Never fabricates."""
    for r in rows:
        hit = []
        if r.get("npi"):
            hit = nppes_lookup(npi=r["npi"], limit=1)
        elif r.get("last_name"):
            hit = nppes_lookup(first=r.get("first_name", ""), last=r["last_name"],
                               state=r.get("state", ""), limit=1)
        r["registry"] = hit[0] if hit and "_error" not in hit[0] else {}
        r["registry_verified"] = bool(r["registry"].get("npi"))
    return rows


# --------------------------------------------------------------- sources ---
# The list does not have to be a file in this repo. Anything that can produce
# CSV over HTTPS works, which covers the three things a team actually has:
#   Google Sheets   File > Share > Publish to web > CSV        -> paste the URL
#   Airtable        share view > CSV download link             -> paste the URL
#   CRM / warehouse  any endpoint or signed S3 URL that returns CSV
# Set DORMANT_URL and the machine reads from there instead of inbox/.
# Column names are the contract either way: name, email, mobile.

def read_url(url: str, timeout: int = 60) -> list[dict]:
    """Fetch a CSV over HTTPS and parse it exactly like a local file."""
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("utf-8-sig", errors="replace")
    rows = [{k.strip(): (v or "").strip() for k, v in row.items() if k}
            for row in csv.DictReader(io.StringIO(text))]
    for row in rows:
        row.setdefault("id", _rid(row))
    return rows


def read_source(name: str, url_env: str = "") -> list[dict]:
    """Resolve one input in priority order, and say out loud where it came from.

        1. an HTTPS URL in the environment   (Sheets, Airtable, CRM export, S3)
        2. inbox/<name>.csv                  (the real list, dropped in)
        3. inbox/<name>.sample.csv           (what ships with the repo)
    """
    url = (os.getenv(url_env) or "").strip() if url_env else ""
    if url:
        try:
            rows = read_url(url)
            print(f"[input]  {len(rows):>5} rows from {url_env} ({url.split('?')[0][:60]})")
            return rows
        except Exception as e:
            # A broken URL must not silently fall back to sample data and look
            # like a successful run against the real list.
            raise RuntimeError(f"{url_env} is set but could not be read: {e}") from e
    for candidate, label in ((f"{name}.csv", "your list"),
                             (f"{name}.sample.csv", "SAMPLE DATA")):
        rows = read_csv(candidate)
        if rows:
            print(f"[input]  {len(rows):>5} rows from inbox/{candidate}  [{label}]")
            return rows
    return []
