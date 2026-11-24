#!/usr/bin/env python3
"""Build an RSS feed of GPU / ML-systems jobs (plus internships / new grad)
that are remote-worldwide or based in Brazil, straight from company job boards.

Usage:  python3 jobs_feed.py            -> writes jobs.xml (+ seen.json state)
        python3 jobs_feed.py --report   -> also prints what matched / why
Stdlib only, no installs.
"""
import json, re, sys, html, datetime as dt, urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.utils import format_datetime
from pathlib import Path

HERE = Path(__file__).parent
OUT, STATE = HERE / "jobs.xml", HERE / "seen.json"

# ---- companies (ats, slug, display name) ---------------------------------
COMPANIES = [
    # frontier labs
    ("greenhouse", "anthropic", "Anthropic"),
    ("ashby", "openai", "OpenAI"),
    ("greenhouse", "xai", "xAI"),
    ("ashby", "thinkingmachines", "Thinking Machines"),
    ("ashby", "cohere", "Cohere"),
    ("ashby", "physicalintelligence", "Physical Intelligence"),
    ("ashby", "perplexity", "Perplexity"),
    ("ashby", "cursor", "Cursor"),
    ("ashby", "cognition", "Cognition"),
    # inference / GPU cloud
    ("ashby", "modal", "Modal"),
    ("greenhouse", "togetherai", "Together AI"),
    ("ashby", "fireworks", "Fireworks AI"),
    ("ashby", "baseten", "Baseten"),
    ("ashby", "fal-ai", "fal"),
    ("ashby", "anyscale", "Anyscale"),
    ("ashby", "lambda", "Lambda"),
    ("greenhouse", "coreweave", "CoreWeave"),
    ("ashby", "crusoe", "Crusoe"),
    ("ashby", "runpod", "Runpod"),
    ("greenhouse", "lightningai", "Lightning AI"),
    ("greenhouse", "databricks", "Databricks"),
    # chips / accelerators
    ("workday", "nvidia", "NVIDIA"),
    ("ashby", "cerebras", "Cerebras"),
    ("ashby", "etched", "Etched"),
    ("ashby", "matx", "MatX"),
    ("ashby", "d-matrix", "d-Matrix"),
    ("greenhouse", "tenstorrent", "Tenstorrent"),
    ("greenhouse", "sambanovasystems", "SambaNova"),
    # quant (heavy low-latency / GPU work)
    ("greenhouse", "janestreet", "Jane Street"),
    ("greenhouse", "wehrtyou", "Hudson River Trading"),
    # Brazil
    ("ashby", "nubank", "Nubank"),
    ("greenhouse", "stone", "Stone"),
    ("greenhouse", "quintoandar", "QuintoAndar"),
    ("greenhouse", "wildlifestudios", "Wildlife Studios"),
]

# ---- filters --------------------------------------------------------------
SYSTEMS = re.compile(r"gpu|cuda|kernel|triton|inference|compiler|accelerat|"
                     r"\bhpc\b|high.performance computing|distributed systems|"
                     r"runtime|ml systems|ml infra|ai infra|training infra|"
                     r"compute infra|performance engineer|model performance|"
                     r"model serving|\bllm\b|numerical", re.I)
# not engineering, or far too senior for early career
SKIP = re.compile(r"manager|director|head of|\blead\b|principal|staff|s[eê]nior|"
                  r"\bsr\.?\b|architect|counsel|recruit|accounting|finance|"
                  r"sales|partnership|analyst|analista|program|product|"
                  r"specialist|support|operations|sourcing|security|"
                  r"policy|adoption|forward deployed|\bit\b", re.I)
EARLY = re.compile(r"intern\b|internship|new.?grad|graduate|university|"
                   r"early.career|entry|junior|resident|residency|fellow|"
                   r"campus|student|est[aá]gi", re.I)
TECH = re.compile(r"engineer|engenheir|research|pesquis|scientist|cientista|"
                  r"developer|desenvolv|software|\bml\b|machine learning|"
                  r"data|dados|quant", re.I)
ML = re.compile(r"machine learning|\bml\b|\bai\b|\bia\b|data scien|"
                r"cientista de dados|research|pesquis|\bllm|deep learning|"
                r"computer vision|\bnlp\b", re.I)
# words that, once removed, should leave a "remote" location empty if it's truly open
OPEN_LOC = re.compile(r"remote|remoto|global|worldwide|anywhere|latam|"
                      r"latin america|brazil|brasil|[-–,/()|;\s]", re.I)
BRAZIL = re.compile(r"brazil|brasil|s[aã]o paulo|rio de janeiro|curitiba|"
                    r"florian[oó]polis|belo horizonte|porto alegre|latam|"
                    r"latin america|south america", re.I)
WORLD = re.compile(r"anywhere|worldwide|global|international", re.I)
REMOTE = re.compile(r"remote|remoto", re.I)
# remote but restricted to a region you can't work from
ELSEWHERE = re.compile(r"\b(us|usa|u\.s\.|united states|canada|uk|united kingdom|"
                       r"europe|emea|eu|india|ind|can|apac|germany|france|japan|"
                       r"china|singapore|korea|australia|israel|poland|serbia|"
                       r"san francisco|new york|seattle|london|toronto|paris|"
                       r"santa clara|mountain view|palo alto|san mateo|bengaluru|"
                       r"middle east|dubai)\b", re.I)


def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "Mozilla/5.0 (job-feed)",
        **({"Content-Type": "application/json"} if data else {})})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def from_greenhouse(slug, name):
    for j in get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")["jobs"]:
        yield dict(id=j["absolute_url"], company=name, title=j["title"],
                   location=(j.get("location") or {}).get("name", ""),
                   remote=None, url=j["absolute_url"],
                   posted=j.get("first_published") or j.get("updated_at"))


def from_ashby(slug, name):
    for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")["jobs"]:
        if not j.get("isListed", True):
            continue
        locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        country = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry", "")
        loc = " / ".join(l for l in locs if l)
        if country and country.lower() not in loc.lower():
            loc += f" ({country})"
        yield dict(id=j["jobUrl"], company=name, title=j["title"], location=loc,
                   remote=j.get("isRemote") or j.get("workplaceType") == "Remote",
                   url=j["jobUrl"], posted=j.get("publishedAt"))


WORKDAY = {"nvidia": ("https://nvidia.wd5.myworkdayjobs.com", "nvidia",
                      "NVIDIAExternalCareerSite")}
WORKDAY_SEARCHES = ["intern", "new college grad", "CUDA", "GPU", "inference",
                    "compiler", "Brazil", "remote"]


def from_workday(slug, name):
    host, tenant, site = WORKDAY[slug]
    api = f"{host}/wday/cxs/{tenant}/{site}/jobs"
    seen = set()
    for q in WORKDAY_SEARCHES:
        for offset in range(0, 100, 20):
            body = json.dumps({"appliedFacets": {}, "limit": 20,
                               "offset": offset, "searchText": q}).encode()
            posts = get(api, body).get("jobPostings", [])
            for p in posts:
                url = f"{host}/en-US/{site}{p['externalPath']}"
                if url in seen:
                    continue
                seen.add(url)
                yield dict(id=url, company=name, title=p["title"],
                           location=p.get("locationsText", ""),
                           remote=None, url=url, posted=None)
            if len(posts) < 20:
                break


SOURCES = {"greenhouse": from_greenhouse, "ashby": from_ashby, "workday": from_workday}


def fetch(company):
    ats, slug, name = company
    try:
        return list(SOURCES[ats](slug, name)), None
    except Exception as e:  # one broken board shouldn't kill the feed
        return [], f"{name}: {e}"


def classify(job):
    t, loc = job["title"], job["location"]
    where = None
    if BRAZIL.search(loc) or BRAZIL.search(t):
        where = "Brazil"
    elif (REMOTE.search(loc) or WORLD.search(loc)) and not OPEN_LOC.sub("", loc):
        where = "Remote"  # location says only "Remote"/"Global"/etc, no country
    if not where or SKIP.search(t) or not TECH.search(t):
        return None
    early, systems, ml = (bool(EARLY.search(t)), bool(SYSTEMS.search(t)),
                          bool(ML.search(t)))
    if not (systems or early or ml):
        return None
    return [where] + [name for name, hit in
                      (("Early career", early), ("Systems", systems), ("ML", ml)) if hit]


def main():
    report = "--report" in sys.argv
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    now = dt.datetime.now(dt.timezone.utc)
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(fetch, COMPANIES))
    errors = [e for _, e in results if e]
    total, items = 0, []
    for jobs, _ in results:
        total += len(jobs)
        for j in jobs:
            tags = classify(j)
            if not tags:
                continue
            first = state.get(j["id"]) or now.isoformat()
            state[j["id"]] = first
            items.append((first, j, tags))
    items.sort(key=lambda x: x[0], reverse=True)

    def esc(s):
        return html.escape(s or "", quote=True)

    rows = []
    for first, j, tags in items:
        pub = format_datetime(dt.datetime.fromisoformat(first))
        rows.append(f"""    <item>
      <title>{esc(j['company'])}: {esc(j['title'])} [{esc(' · '.join(tags))}]</title>
      <link>{esc(j['url'])}</link>
      <guid isPermaLink="true">{esc(j['url'])}</guid>
      <pubDate>{pub}</pubDate>
      <category>{esc(j['company'])}</category>
      <description>{esc(j['company'])} · {esc(j['location'] or 'location not listed')} · {esc(' · '.join(tags))}</description>
    </item>""")
    OUT.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Jobs: GPU / ML systems · early career · Remote or Brazil</title>
    <link>https://feeds.augustodoregofranke.com/jobs.xml</link>
    <description>Filtered from {len(COMPANIES)} company job boards</description>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
{chr(10).join(rows)}
  </channel>
</rss>
""", encoding="utf-8")
    # keep state for jobs still open only
    live = {j["id"] for jobs, _ in results for j in jobs}
    STATE.write_text(json.dumps({k: v for k, v in state.items() if k in live}, indent=0))

    print(f"{total} jobs scanned from {len(COMPANIES)} companies -> {len(items)} in feed")
    for e in errors:
        print("  error:", e)
    if report:
        for _, j, tags in items:
            print(f"  [{' · '.join(tags)}] {j['company']}: {j['title']}  —  {j['location']}")


if __name__ == "__main__":
    main()
