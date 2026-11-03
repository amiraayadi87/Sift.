# ======================================================================
# Fewer daily feed collector
#
#   python fewer_feed.py plan  --state state/ --out plan.json
#   python fewer_feed.py build --state state/ --raw raw/ --out out/
#
# state/  config.json   (Fewer db doc config/search, as saved by ArtifactData)
#         wants/*.json  (Fewer db collection "wants": one doc per user who shares roles/places)
#         feed/*.json   (current Fewer db collection "feed")
#         status.json   (Fewer db doc config/status, optional)
# raw/    companies*.txt / companies*.json   (saved get-dataset-items output, factpipe/ats-jobs-feed)
#         linkedin*.txt / linkedin*.json     (saved get-dataset-items output, valig/linkedin-jobs-scraper)
#
# build writes out/manifest.json: batches of ArtifactData writes (each <=50 entries, <=~800KB)
# that point at out/docs/<id>.json files, plus out/report.json with counts and dropped-by-rule.
# ======================================================================
import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

SETTINGS = {
    "posted_within_days": 2,      # how fresh a job must be (company-site search window)
    "keep_days": 10,              # feed keeps jobs found in the last N days
    "max_feed": 600,              # hard cap on feed size
    "companies_max_results": 200, # factpipe cap per run (~$0.003 each)
    "linkedin_limit": 100,        # per LinkedIn run (~$0.0004 each)
    "max_roles": 12,
    "advert_chars": 12000,
}

SENIOR_TITLE = re.compile(r"\b(senior|snr|sr\.?|lead|principal|head of|director|vp|avp|svp|evp|vice president|chief|staff|group product|cpo|cto|cfo)\b", re.I)
ENGLISH_COUNTRY = {"GB": "United Kingdom", "IE": "Ireland", "DE": "Germany", "FR": "France", "NL": "Netherlands",
                   "BE": "Belgium", "LU": "Luxembourg", "ES": "Spain", "PT": "Portugal", "IT": "Italy", "AT": "Austria",
                   "CH": "Switzerland", "SE": "Sweden", "NO": "Norway", "DK": "Denmark", "FI": "Finland", "PL": "Poland",
                   "CZ": "Czechia", "HU": "Hungary", "RO": "Romania", "GR": "Greece", "EE": "Estonia", "LV": "Latvia",
                   "LT": "Lithuania", "HR": "Croatia", "SI": "Slovenia", "SK": "Slovakia", "BG": "Bulgaria", "CY": "Cyprus", "MT": "Malta"}
SENIOR_EXCLUDE = ["senior", "lead", "principal", "head", "director", "staff", "vp", "chief"]
ROLE_STOP = {"junior", "graduate", "grad", "entry", "level", "trainee", "assistant", "associate", "the", "and", "of",
             "in", "for", "a", "an", "roles", "role", "jobs", "job"}
SCAM = re.compile(r"\b(registration|admin(istration)?|training|starter|onboarding|application|processing)\s+fee\b"
                  r"|\b(pay|paying|payment of)\s+(a|an|the)?\s*(fee|deposit)\b|\bupfront (payment|cost)\b"
                  r"|\bsend (us )?(a copy of )?your (passport|bank|national insurance)\b|\bwork from home and earn\b", re.I)
SITE_RANK = {"Company site": 0, "Indeed": 1, "LinkedIn": 2, "Glassdoor": 3, "Reed": 4, "Welcome to the Jungle": 5, "hirebase": 6, "Adzuna": 7}
PLACEHOLDER_COMPANY = re.compile(r"^\s*(referrals? only|internal( only| applicants)?|confidential|not disclosed|undisclosed|stealth( company| startup)?|company|employer|n/?a)\s*$", re.I)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- reading saved tool output
def load_items(path):
    """Read a saved get-dataset-items / ArtifactData result. Accepts raw JSON, {"items": [...]},
    a bare list, or tool text with the JSON inside it."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    data = None
    try:
        data = json.loads(text)
    except Exception:
        for opener in ("{", "["):
            i = text.find(opener)
            while i != -1:
                try:
                    data = json.JSONDecoder().raw_decode(text[i:])[0]
                    break
                except Exception:
                    i = text.find(opener, i + 1)
            if data is not None:
                break
    if data is None:
        return []
    # some tool results wrap the payload as [{"type":"text","text":"{...}"}]
    if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("type") == "text":
        merged = []
        for part in data:
            tmp = path + ".part"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(part.get("text", ""))
            merged += load_items(tmp)
            os.remove(tmp)
        return merged
    if isinstance(data, dict):
        for key in ("items", "documents", "docs", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return data if isinstance(data, list) else []


def doc_body(d):
    """ArtifactData documents look like {"id","data","version"}; also accept plain bodies."""
    if isinstance(d, dict) and isinstance(d.get("data"), dict):
        return d["data"]
    return d


def load_dir_docs(folder):
    docs = []
    for p in sorted(glob.glob(os.path.join(folder, "**", "*.json"), recursive=True)):
        for item in load_items(p):
            if isinstance(item, dict):
                if "id" not in item or "data" not in item:
                    # ArtifactData out_dir files hold just the body, named <doc_id>.json. Feed jobs are written
                    # once and never edited, so their version is 1 (needed to delete them later).
                    item = {"id": os.path.splitext(os.path.basename(p))[0], "data": doc_body(item), "version": item.get("version") or 1}
                docs.append(item)
    return docs


# ---------------------------------------------------------------- what users want
def role_words(role):
    return [w for w in re.split(r"[^a-z0-9+#]+", role.lower()) if len(w) > 1 and w not in ROLE_STOP]


CHANGES_THE_JOB = {"marketing", "sales", "account", "project", "programme", "program", "owner", "designer", "design",
                   "support", "recruitment", "recruiter", "teacher", "security", "network", "facilities"}


_SUFFIXES = ("ments", "ment", "ers", "er", "ing", "ics", "ist", "ists", "s", "e")


def stem(word):
    """management/manager -> manag, analytics/analyst -> analy(t), engineering/engineer -> engine"""
    w = word.lower()
    for suf in _SUFFIXES:
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    if len(w) > 5 and w.endswith("e"):
        w = w[:-1]
    return w


def _same(a, b):
    sa, sb = stem(a), stem(b)
    return sa == sb or (min(len(sa), len(sb)) >= 5 and (sa.startswith(sb) or sb.startswith(sa)))


def role_matches(title, role):
    """'Data Analyst' matches 'Junior Data Analyst', 'Sales Data Analyst' and 'Data & Insights Analyst';
    'Product Management' matches 'Product Manager'; 'product manager' does not match 'Product Marketing Manager'."""
    tw = re.findall(r"[a-z0-9+#]+", title.lower())
    words = role_words(role)
    if not words:
        return False
    pos = []
    for w in words:
        hits = [i for i, t in enumerate(tw) if _same(t, w)]
        if not hits:
            return False
        pos.append(hits)
    # the words appear together, in order
    if any(all(p + k in pos[k] for k in range(len(words))) for p in pos[0]):
        return True
    used = {i for hits in pos for i in hits}
    extra = {t for i, t in enumerate(tw) if i not in used}
    return not (extra & CHANGES_THE_JOB)


ROLE_VARIANTS = {"management": "manager", "analytics": "analyst", "engineering": "engineer", "development": "developer",
                 "design": "designer", "consulting": "consultant", "accounting": "accountant", "research": "researcher"}


def search_terms(role):
    """Extra phrasings for keyword searches: 'Product Management' also searches 'Product Manager'."""
    out = [role]
    low = role.lower()
    for a, b in ROLE_VARIANTS.items():
        if re.search(r"\b" + a + r"\b", low):
            out.append(re.sub(r"\b" + a + r"\b", b, low))
    return out


def place_to_countries(place):
    p = (place or "").strip()
    if not p:
        return set()
    f = fold(p)
    if f in ("remote", "anywhere", "remote uk", "uk remote"):
        return {"GB"}
    if f in ("europe", "eu", "emea", "remote europe", "remote eu"):
        return set(EUROPE) | {"EU"}
    code, _ = locate(p)
    if code:
        return {code}
    return {"GB"} if not looks_non_european(p) else set()


def gather_wants(state_dir):
    """Owner searches + every shared user want -> list of {roles, countries, remote, entryOnly, places}."""
    wants = []
    cfg_path = os.path.join(state_dir, "config.json")
    if not os.path.exists(cfg_path):  # ArtifactData out_dir layout: state/config/config/search.json
        hits = glob.glob(os.path.join(state_dir, "**", "search.json"), recursive=True)
        cfg_path = hits[0] if hits else cfg_path
    if os.path.exists(cfg_path):
        items = load_items(cfg_path)
        body = doc_body(items[0]) if items else {}
        for s in body.get("searches", []) or []:
            kw = str(s.get("keywords", "")).strip()
            if kw:
                wants.append({"roles": [kw], "countries": place_to_countries(s.get("location") or "United Kingdom") or {"GB"},
                              "places": [s.get("location") or "United Kingdom"], "entryOnly": True,
                              "patterns": ["remote", "hybrid", "on-site"], "who": "owner"})
    for d in load_dir_docs(os.path.join(state_dir, "wants")):
        body = doc_body(d)
        roles = [str(r).strip() for r in (body.get("roles") or []) if str(r).strip()]
        if not roles:
            continue
        places = [str(p) for p in (body.get("locations") or [])]
        countries = set()
        for p in places:
            countries |= place_to_countries(p)
        if not countries:
            countries = {"GB"}
        if any(fold(p) == "remote" for p in places) or "remote" in (body.get("patterns") or []):
            countries.add("EU")  # "Remote - Europe/EMEA" roles; Fewer's fit check confirms they accept the user's country
        wants.append({"roles": roles[:8], "countries": countries, "places": places,
                      "entryOnly": bool(body.get("entryOnly", True)),
                      "patterns": body.get("patterns") or ["remote", "hybrid", "on-site"], "who": d.get("id", "")})
    return wants


def plan(wants, settings=SETTINGS):
    roles, seen = [], set()
    for w in wants:
        for r in w["roles"]:
            for term in search_terms(r):
                # search the core words ("graduate data analyst" -> "data analyst"); seniority is filtered in code
                term = " ".join(role_words(term)) or term.lower()
                if term.lower() not in seen:
                    seen.add(term.lower())
                    roles.append(term)
    # roles covered by a shorter role are redundant in the search ("junior product management" ⊂ "product manager")
    roles = [r for r in roles if not any(o != r and role_matches(r, o) and len(o.split()) < len(r.split()) for o in roles)]
    roles = roles[: settings["max_roles"]]
    countries = set()
    for w in wants:
        countries |= w["countries"]
    countries.discard("EU")
    all_entry = bool(wants) and all(w["entryOnly"] for w in wants)
    companies = {
        "keywords": roles, "keywordMatch": "any", "keywordScope": "title",
        "locations": sorted(countries) or ["GB"], "postedWithinDays": settings["posted_within_days"],
        "maxResults": settings["companies_max_results"], "maxPerCompany": 3, "includeDescription": True,
    }
    if all_entry:
        companies["excludeKeywords"] = SENIOR_EXCLUDE
    # LinkedIn: one run per country (its location field takes one place); UK first, at most 3 runs
    li_runs = []
    for c in (["GB"] if "GB" in countries else []) + sorted(countries - {"GB"}):
        if len(li_runs) >= 3:
            break
        quoted = " OR ".join(f'"{r}"' for r in roles)
        kw = f"({quoted})" + (" NOT (senior OR lead OR principal OR head OR director OR staff)" if all_entry else "")
        li_runs.append({"keywords": kw, "location": ENGLISH_COUNTRY.get(c, c),
                        "datePosted": "r86400", "limit": settings["linkedin_limit"], "easyApply": False, "under10Applicants": False})
    return {"roles": roles, "countries": sorted(countries), "allEntryOnly": all_entry,
            "companies_input": companies, "linkedin_inputs": li_runs if roles else []}


# ---------------------------------------------------------------- facts from adverts
YEARS = re.compile(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)(?:'|’)?\s+(?:of\s+)?(?:\w+\s+){0,4}?(?:experience|exp\b)", re.I)
VISA_NO = re.compile(r"(unable to|cannot|can't|can not|do not|don't|will not|won't|not able to)\s+(offer\s+|provide\s+)?(visa\s+)?sponsor|no (visa )?sponsorship|sponsorship (is )?not (available|offered|provided)|must (already )?have (the )?(full |existing )?right to work", re.I)
VISA_YES = re.compile(r"(visa )?sponsorship (is )?(available|offered|provided)|(we|can|will) (can )?sponsor (your |a )?visa|skilled worker visa sponsorship|offer visa sponsorship", re.I)
LANG = re.compile(r"\b(fluent|native|business[- ]level|proficient|professional[- ]level|excellent|strong)\s+(?:written and spoken\s+|spoken and written\s+)?(german|french|dutch|spanish|italian|portuguese|polish|swedish|danish|norwegian|finnish|czech|hungarian|romanian|greek|arabic|mandarin|japanese)\b"
                  r"|\b(german|french|dutch|spanish|italian|portuguese|polish|swedish|danish|norwegian|finnish|czech)\s*(?:\(|-|:)?\s*(?:c1|c2|b2|fluent|native)\b", re.I)
CLOSING = re.compile(r"(closing date|apply by|applications close|deadline)[:\s]+(?:on\s+)?(\d{1,2}(?:st|nd|rd|th)?\s+\w+\s*\d{0,4}|\d{1,2}/\d{1,2}/\d{2,4})", re.I)
MONEY = re.compile(r"([£€])\s?(\d{2,3}(?:[,.]\d{3})|\d{2,3}\s?[kK])(?:\s?(?:-|–|to)\s?[£€]?\s?(\d{2,3}(?:[,.]\d{3})|\d{2,3}\s?[kK]))?")
PATTERN_WORDS = [("hybrid", re.compile(r"\bhybrid\b", re.I)),
                 ("remote", re.compile(r"\b(fully remote|remote[- ]first|100% remote|work from anywhere|remote role|remote position|remote \(uk\)|uk remote|remote within)\b", re.I)),
                 ("on-site", re.compile(r"\b(on[- ]?site|in[- ]office|office[- ]based|5 days (a week )?in (the )?office)\b", re.I))]


def _num(s):
    s = s.replace(",", "").replace(".", "").replace(" ", "").lower()
    return float(s[:-1]) * 1000 if s.endswith("k") else float(s)


def extract_facts(title, text, location, hints=None):
    hints = hints or {}
    t = (text or "")
    facts = {}
    # work pattern: the source's own field first, then the advert
    wp = (hints.get("workplace") or "").lower()
    if wp in ("remote", "hybrid", "onsite", "on-site", "on_site"):
        facts["pattern"] = "on-site" if wp.startswith("on") else wp
    else:
        for name, rx in PATTERN_WORDS:
            if rx.search(title + " " + location) or rx.search(t[:6000]):
                facts["pattern"] = name
                break
        else:
            facts["pattern"] = "unknown"
    y = hints.get("yearsMin")
    if y is None:
        ys = [int(m.group(1)) for m in YEARS.finditer(t[:8000]) if 0 < int(m.group(1)) < 20]
        y = min(ys) if ys else None
    if y is not None:
        facts["yearsMin"] = int(y)
    v = hints.get("visa")
    if v is None:
        if VISA_NO.search(t):
            v = False
        elif VISA_YES.search(t):
            v = True
    if v is not None:
        facts["visa"] = bool(v)
    # a language is a requirement unless the advert calls it a plus/desirable/nice to have nearby
    optional = re.compile(r"\b(plus|bonus|desirable|nice[- ]to[- ]have|advantage|advantageous|preferred|ideally|beneficial|helpful)\b", re.I)
    langs = sorted({(m.group(2) or m.group(3) or "").title() for m in LANG.finditer(t)
                    if (m.group(2) or m.group(3)) and not optional.search(t[max(0, m.start() - 40): m.end() + 40])})
    if langs:
        facts["languages"] = langs
    m = CLOSING.search(t)
    if m:
        facts["closing"] = m.group(2).strip()
    lo, hi, cur = hints.get("salaryMin"), hints.get("salaryMax"), hints.get("currency")
    if not lo and not hi:
        m = MONEY.search(t[:8000])
        if m:
            try:
                lo = _num(m.group(2))
                hi = _num(m.group(3)) if m.group(3) else None
                cur = "GBP" if m.group(1) == "£" else "EUR"
                if lo < 10000 or (hi and hi < lo):  # day rates / noise
                    lo = hi = None
            except Exception:
                lo = hi = None
    if lo or hi:
        facts["salaryMin"], facts["salaryMax"], facts["currency"] = lo, hi, cur or ""
    if SENIOR_TITLE.search(title):
        facts["level"] = "senior"
    elif re.search(r"\b(graduate|grad|junior|jr|entry[- ]level|associate|trainee|apprentice|intern)\b", title, re.I):
        facts["level"] = "entry"
    if SCAM.search(t):
        facts["scam"] = True
    return facts


def salary_text(f):
    lo, hi, cur = f.get("salaryMin"), f.get("salaryMax"), f.get("currency", "")
    sym = {"GBP": "£", "EUR": "€", "USD": "$", "CHF": "CHF "}.get(cur, "")
    fmt = lambda v: f"{sym}{v:,.0f}"  # noqa: E731
    if lo and hi and abs(lo - hi) > 1:
        return f"{fmt(lo)} – {fmt(hi)}"
    if lo or hi:
        return fmt(lo or hi)
    return ""


# ---------------------------------------------------------------- normalising each source
def from_companies(it):
    locs = it.get("locations") or []
    codes = it.get("country_codes") or []
    loc = "; ".join(locs)
    country, city = "", ""
    for text, cc in zip(locs + [""] * len(codes), codes or [""] * len(locs)):
        country, city = locate(text, cc)
        if country:
            break
    if not country and codes:
        country = codes[0] if codes[0] in EUROPE else ""
    return {
        "site": "Company site", "ats": it.get("ats", ""), "title": (it.get("title") or "").strip(),
        "company": (it.get("company_name") or "").strip(), "location": loc, "country": country, "city": city,
        "url": it.get("job_url") or it.get("apply_url") or "", "applyUrl": it.get("apply_url") or "",
        "postedAt": it.get("posted_at") or "",
        "advert": it.get("description_text") or it.get("description_snippet") or "",
        "hints": {"workplace": it.get("workplace_type"), "yearsMin": it.get("years_experience_min"),
                  "visa": it.get("visa_sponsorship"), "salaryMin": it.get("salary_min"), "salaryMax": it.get("salary_max"),
                  "currency": it.get("salary_currency")},
        "remote": bool(it.get("remote")),
    }


def from_linkedin(it):
    loc = it.get("location") or ""
    country, city = locate(loc)
    jid = str(it.get("id") or "")
    wt = (it.get("workType") or "").lower()
    return {
        "site": "LinkedIn", "ats": "linkedin", "title": (it.get("title") or "").strip(),
        "company": (it.get("companyName") or "").strip(), "location": loc, "country": country, "city": city,
        "url": it.get("url") or (f"https://www.linkedin.com/jobs/view/{jid}" if jid else ""),
        "applyUrl": it.get("applyUrl") or "", "postedAt": it.get("postedDate") or "",
        "advert": it.get("description") or "",
        "hints": {"workplace": "remote" if "remote" in wt or "remote" in loc.lower() else ("hybrid" if "hybrid" in wt or "hybrid" in loc.lower() else ("on-site" if "on-site" in wt or "onsite" in wt else None))},
        "remote": "remote" in wt or "remote" in loc.lower(),
        "salaryText": it.get("salary") or "",
    }


# ---------------------------------------------------------------- build the feed
def job_id(company, title, place):
    key = "|".join([norm_company(company), norm_title(title), (place or "").lower()])
    return "j" + hashlib.sha1(key.encode()).hexdigest()[:20]


def build(state_dir, raw_dir, out_dir, settings=SETTINGS, today=None):
    found_at = today or now_iso()
    wants = gather_wants(state_dir)
    report = {"foundAt": found_at, "fetched": {}, "dropped": {}, "added": 0, "kept_existing": 0, "removed_old": 0,
              "duplicates": 0, "wants": len(wants), "roles": plan(wants, settings)["roles"]}

    def drop(rule):
        report["dropped"][rule] = report["dropped"].get(rule, 0) + 1

    raw = load_raw(raw_dir, report)
    candidates = select_jobs(raw, wants, settings, report, drop, found_at)
    existing = {d["id"]: d for d in load_dir_docs(os.path.join(state_dir, "feed"))}
    return _write_fewer(candidates, existing, report, out_dir, settings)


def _g(it, path, default=""):
    """Read 'employer.name' style fields, from nested objects or already-flattened keys."""
    if path in it:
        return it[path] if it[path] is not None else default
    cur = it
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[0] if cur else {}
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    if isinstance(cur, list):
        cur = cur[0] if cur else default
    return default if cur is None else cur


def _board(site, title, company, location, url, posted="", pattern=None, salary=""):
    """UK job boards searched for the UK: no advert text, small towns default to GB."""
    country, city = locate(location)
    if not country and not looks_non_european(location):
        country = "GB"
    return {"site": site, "ats": site.lower(), "title": str(title or "").strip(), "company": str(company or "").strip(),
            "location": str(location or "").strip(), "country": country, "city": city, "url": str(url or "").strip(),
            "applyUrl": "", "postedAt": str(posted or ""), "advert": "", "noAdvert": True,
            "hints": {"workplace": pattern}, "remote": pattern == "remote", "salaryText": salary}


def _pattern(*texts):
    t = " ".join(str(x or "") for x in texts).lower()
    return "remote" if ("remote" in t or "fulltime" == t.strip()) else ("hybrid" if ("hybrid" in t or "partial" in t) else None)


def from_indeed(it):
    lo, hi, unit = _g(it, "baseSalary.min"), _g(it, "baseSalary.max"), _g(it, "baseSalary.unitOfWork")
    sal = f"£{lo:,.0f} - £{hi:,.0f}/{str(unit).lower()}" if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) else ""
    return _board("Indeed", _g(it, "title"), _g(it, "employer.name"), _g(it, "location.city") or "United Kingdom",
                  _g(it, "jobUrl"), salary=sal)


def from_reed(it):
    loc = _g(it, "location")
    pat = "remote" if _g(it, "is_remote") is True or str(_g(it, "location_type")).lower() == "remote" else _pattern(_g(it, "location_type"))
    return _board("Reed", _g(it, "title"), _g(it, "recruiter_name"), loc, _g(it, "job_url"), _g(it, "posted_date"), pat)


def from_glassdoor(it):
    loc = re.sub(r",\s*England$", "", str(_g(it, "location.name")))
    return _board("Glassdoor", _g(it, "title"), _g(it, "employer.name"), loc, _g(it, "url"))


def from_wttj(it):
    loc = ", ".join(x for x in [str(_g(it, "offices.city")), str(_g(it, "offices.country"))] if x)
    return _board("Welcome to the Jungle", _g(it, "name"), _g(it, "organizationName"), loc, _g(it, "url"),
                  _g(it, "publishedAt"), _pattern(_g(it, "remote")))


def from_hirebase(it):
    return _board("hirebase", _g(it, "jobTitle"), _g(it, "companyName"), _g(it, "location"), _g(it, "applicationLink"),
                  _g(it, "datePosted"), _pattern(_g(it, "locationType")))


def from_adzuna_row(row):
    """A row from the PM sheet's All jobs tab: A date, B search, C title, D company, E location, F salary, G link."""
    r = list(row) + [""] * 10
    return _board("Adzuna", r[2], r[3], r[4], r[6], r[0], salary="" if r[5] == "Not stated" else r[5])


SOURCES = [("companies*", from_companies, "Company site"), ("linkedin*", from_linkedin, "LinkedIn"),
           ("indeed*", from_indeed, "Indeed"), ("reed*", from_reed, "Reed"), ("glassdoor*", from_glassdoor, "Glassdoor"),
           ("wttj*", from_wttj, "Welcome to the Jungle"), ("hirebase*", from_hirebase, "hirebase")]


def load_raw(raw_dir, report):
    raw = []
    for p in sorted(glob.glob(os.path.join(raw_dir, "adzuna*"))):
        rows = read_sheet_rows(p)
        sel = [r for r in rows if len(r) > 9 and str(r[9]).strip().lower() == "adzuna" and not str(r[8]).strip()]
        raw += [from_adzuna_row(r) for r in sel]
        report["fetched"]["Adzuna"] = report["fetched"].get("Adzuna", 0) + len(sel)
    for pattern, fn, name in SOURCES:
        n = 0
        for p in sorted(glob.glob(os.path.join(raw_dir, pattern))):
            for it in load_items(p):
                if isinstance(it, dict):
                    raw.append(fn(it))
                    n += 1
        if n or name in ("Company site", "LinkedIn"):
            report["fetched"][name] = n
    return raw


def read_sheet_rows(path):
    """All rows (header excluded) of a saved Google Sheets get_values result."""
    for item in [load_items(path)]:
        if isinstance(item, list) and item and isinstance(item[0], dict) and "values" in item[0]:
            return item[0]["values"][1:]
        if isinstance(item, list) and item and isinstance(item[0], list):
            return item[1:]
    return []


def _all(matched, test):
    """A job is dropped by a personal rule only when it fails that rule for everyone it matched."""
    return all(test(w) for w in matched)


def select_jobs(raw, wants, settings, report, drop, found_at):
    """The code filter. Returns {job_id: (source_rank, doc)} for jobs that pass."""
    allowed = set()
    for w in wants:
        allowed |= w["countries"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=settings["posted_within_days"] + 5)).date().isoformat()
    candidates = {}
    for j in raw:
        if not j["title"] or not j["url"] or not j["company"]:
            drop("missing title, company or link")
            continue
        if PLACEHOLDER_COMPANY.search(j["company"]):
            drop("placeholder employer name (referrals-only or hidden board)")
            continue
        if not j["country"] and j.get("remote") and not looks_non_european(j["location"]):
            j["country"] = "EU" if "EU" in allowed else ""
        if not j["country"]:
            drop("not UK or Europe" if j["location"] else "no location")
            continue
        if j["country"] not in allowed:
            drop("country nobody asked for")
            continue
        matched = [w for w in wants if any(role_matches(j["title"], r) for r in w["roles"])
                   and (j["country"] in w["countries"] or (j["country"] == "EU" and "EU" in w["countries"]))]
        if not matched:
            drop("title doesn't match anyone's roles")
            continue
        text = j["advert"]
        facts = extract_facts(j["title"], text, j["location"], j.get("hints"))
        if facts.get("scam"):
            drop("asks for a fee or ID documents (likely scam)")
            continue
        if facts.get("level") == "senior" and all(w["entryOnly"] for w in matched):
            drop("senior title, everyone matching wants entry level")
            continue
        if facts.get("yearsMin", 0) >= 5 and all(w["entryOnly"] for w in matched):
            drop("asks for 5+ years, everyone matching wants entry level")
            continue
        if facts["pattern"] != "unknown" and all(facts["pattern"] not in (w["patterns"] or [facts["pattern"]]) for w in matched):
            drop("work pattern nobody accepts")
            continue
        tl = j["title"].lower()
        hit = [x for w in matched for x in w.get("exclude", []) if x and re.search(r"(?<![a-z])" + re.escape(x.lower()) + r"(?![a-z])", tl)]
        if hit and _all(matched, lambda w: any(x.lower() in hit for x in w.get("exclude", []))):
            drop("a role you said no to (" + hit[0] + ")")
            continue
        if facts.get("yearsMin") is not None and _all(matched, lambda w: w.get("maxYears") is not None and facts["yearsMin"] > w["maxYears"]):
            drop("asks for more years of experience than you set")
            continue
        if facts.get("visa") is False and _all(matched, lambda w: w.get("needsVisa")):
            drop("says it can't sponsor a visa, and you need one")
            continue
        langs = [l for l in facts.get("languages", []) if l.lower() != "english"]
        if langs and _all(matched, lambda w: w.get("fluent") is not None and any(l.lower() not in w["fluent"] for l in langs)):
            drop("needs a language you're not fluent in")
            continue
        posted = (j["postedAt"] or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", posted) and posted < cutoff:
            drop("too old")
            continue
        if not j.get("noAdvert") and len(text.strip()) < 200:
            drop("advert text too short to judge")
            continue
        facts["agency"] = looks_like_agency(j["company"]) or bool(re.search(r"\bour client\b", text[:1500], re.I))
        facts["country"] = j["country"]
        if j["city"]:
            facts["city"] = j["city"]
        sal = salary_text(facts) or j.get("salaryText", "")
        doc = {
            "title": j["title"][:200], "company": j["company"][:120], "location": j["location"][:200],
            "salary": sal or "Not stated", "url": j["url"], "applyUrl": j.get("applyUrl", ""),
            "site": j["site"] + (f" ({j['ats'].title()})" if j["site"] == "Company site" and j["ats"] else ""),
            "postedAt": j["postedAt"], "foundAt": found_at,
            "advert": html_to_text(text, settings["advert_chars"]) if "<" in text[:2000] else text[: settings["advert_chars"]],
            "facts": facts,
            "roles": sorted({r for w in matched for r in w["roles"] if role_matches(j["title"], r)}),
        }
        # same company + title + country = same job (sources name the city differently: "Nous HQ" vs "London")
        did = job_id(j["company"], j["title"], j["country"])
        rank = SITE_RANK.get(j["site"], 9)
        if did in candidates:
            report["duplicates"] += 1
            if rank >= candidates[did][0]:
                continue
        candidates[did] = (rank, doc)
    return candidates


def _write_fewer(candidates, existing, report, out_dir, settings):
    # anything already in the feed is kept as it is (its foundAt stays the day it first appeared)
    writes, new_ids = [], []
    os.makedirs(os.path.join(out_dir, "docs"), exist_ok=True)
    for did, (_, doc) in candidates.items():
        if did in existing:
            report["kept_existing"] += 1
            continue
        path = os.path.join(out_dir, "docs", did + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        writes.append({"op": "set", "collection": "feed", "doc_id": did, "file_path": os.path.abspath(path),
                       "_bytes": os.path.getsize(path)})
        new_ids.append(did)
    report["added"] = len(new_ids)

    # remove old jobs, and the oldest ones if the feed would grow past max_feed
    keep_after = (datetime.now(timezone.utc) - timedelta(days=settings["keep_days"])).isoformat()
    live = []
    for did, d in existing.items():
        body = doc_body(d)
        fa = str(body.get("foundAt", ""))
        if fa and fa < keep_after:
            writes.append({"op": "delete", "collection": "feed", "doc_id": did, "if_version": d.get("version"), "_bytes": 100})
            report["removed_old"] += 1
        else:
            live.append((fa, did, d))
    overflow = len(live) + len(new_ids) - settings["max_feed"]
    if overflow > 0:
        for fa, did, d in sorted(live)[:overflow]:
            writes.append({"op": "delete", "collection": "feed", "doc_id": did, "if_version": d.get("version"), "_bytes": 100})
            report["removed_old"] += 1
    report["feedSize"] = len(live) + len(new_ids) - max(overflow, 0)

    # batches: <=50 writes and <=800KB each
    batches, cur, size = [], [], 0
    for w in writes:
        if cur and (len(cur) >= 50 or size + w["_bytes"] > 800_000):
            batches.append(cur)
            cur, size = [], 0
        size += w["_bytes"]
        cur.append({k: v for k, v in w.items() if not k.startswith("_") and v is not None})
    if cur:
        batches.append(cur)

    status = {"lastRun": report["foundAt"], "added": report["added"], "feedSize": report["feedSize"],
              "fetched": report["fetched"], "dropped": report["dropped"], "duplicates": report["duplicates"],
              "searchedRoles": report["roles"], "failures": []}
    with open(os.path.join(out_dir, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"batches": batches, "status_file": os.path.abspath(os.path.join(out_dir, "status.json"))}, f, indent=1)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    return report, batches


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fewer daily feed collector")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--state", required=True)
    p.add_argument("--out", default="plan.json")
    b = sub.add_parser("build")
    b.add_argument("--state", required=True)
    b.add_argument("--raw", required=True)
    b.add_argument("--out", default="out")
    w = sub.add_parser("batch", help="print upload batch N (1-based) as the JSON 'writes' list for ArtifactData")
    w.add_argument("--manifest", default="out/manifest.json")
    w.add_argument("--n", type=int, required=True)
    f = sub.add_parser("fail", help="record a failed source in out/status.json")
    f.add_argument("--out", default="out")
    f.add_argument("message")
    a = ap.parse_args(argv)
    if a.cmd == "batch":
        m = json.load(open(a.manifest, encoding="utf-8"))
        print(f"{len(m['batches'])} batch(es)", file=sys.stderr)
        if 1 <= a.n <= len(m["batches"]):
            print(json.dumps(m["batches"][a.n - 1], separators=(",", ":")))
        return 0
    if a.cmd == "fail":
        p = os.path.join(a.out, "status.json")
        st = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"lastRun": now_iso(), "added": 0, "failures": []}
        st.setdefault("failures", []).append(a.message[:200])
        json.dump(st, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        print("recorded")
        return 0
    if a.cmd == "plan":
        wants = gather_wants(a.state)
        pl = plan(wants)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(pl, f, indent=1)
        print(f"{len(wants)} wants -> roles: {', '.join(pl['roles']) or 'none'}; countries: {', '.join(pl['countries']) or 'none'}; "
              f"LinkedIn runs: {len(pl['linkedin_inputs'])}. Inputs saved to {a.out}")
    else:
        report, batches = build(a.state, a.raw, a.out)
        print(f"Fetched {report['fetched']}; added {report['added']} new; {report['kept_existing']} already in feed; "
              f"{report['duplicates']} duplicates; removed {report['removed_old']} old; feed size {report['feedSize']}.")
        print("Dropped by rule: " + (", ".join(f"{k} {v}" for k, v in sorted(report["dropped"].items(), key=lambda x: -x[1])) or "none"))
        print(f"{len(batches)} upload batch(es) in {os.path.join(a.out, 'manifest.json')}")
    return 0

