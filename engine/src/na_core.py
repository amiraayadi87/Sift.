# ======================================================================
# na: sheet + database mode
#
# The Google Sheet and na's built-in database hold the same four tables with the same
# columns (SCHEMA below). Sheet tab <-> database collection, sheet row <-> document.
#
#   python na_engine.py na-plan  --search search.json --me me.json --out plan.json
#   python na_engine.py na-build --search search.json --me me.json --feed feed.json --raw raw --out out
#   python na_engine.py na-rows  --out out --n 1      # print sheet rows to append (chunks of 40)
#   python na_engine.py na-db    --out out --n 1      # print database writes for the new rows (chunks of 50)
#
# search.json / me.json / feed.json are saved Google Sheets get_values results
# ({"range": ..., "values": [[...], ...]}) for Search!A1:C40, Me!A1:C60 and Feed!A1:S5000.
# ======================================================================

SCHEMA = {
    "Search": {"collection": "search", "key": "setting", "columns": [
        ["Setting", "setting"], ["Value", "value"], ["What it does", "help"]]},
    "Me": {"collection": "me", "key": "fact", "columns": [
        ["Fact", "fact"], ["Value", "value"], ["Used for", "usedFor"]]},
    "Feed": {"collection": "feed", "key": "jobId", "columns": [
        ["Date found", "dateFound"], ["Source", "source"], ["Job title", "title"], ["Company", "company"],
        ["Location", "location"], ["Salary", "salary"], ["Link", "link"], ["Facts", "facts"],
        ["Role searched", "role"], ["Decision", "decision"], ["Reason", "reason"], ["Requirements", "requirements"],
        ["CV", "cv"], ["CV score", "cvScore"], ["Status", "status"], ["Note", "note"],
        ["Date applied", "dateApplied"], ["Posted", "posted"], ["Job ID", "jobId"]]},
    "Runs": {"collection": "runs", "key": None, "columns": [
        ["When", "when"], ["Step", "step"], ["Summary", "summary"], ["Problems", "problems"]]},
}


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", fold(text or "")).strip("-")
    return s[:120] or "x"


def doc_id_for(tab, fields, row_number):
    """The database document id for a sheet row: same rule in the engine and the app."""
    key = SCHEMA[tab]["key"]
    if tab == "Runs":
        return f"r{row_number:06d}"
    val = str(fields.get(key, "")).strip()
    if tab == "Feed":
        return val if re.fullmatch(r"[A-Za-z0-9_\-]{1,120}", val or "") else f"row{row_number:06d}"
    return slug(val) if val else f"row{row_number:06d}"


def row_to_doc(tab, values, row_number):
    cols = SCHEMA[tab]["columns"]
    fields = {}
    for i, (_, name) in enumerate(cols):
        v = values[i] if i < len(values) else ""
        fields[name] = "" if v is None else (v if isinstance(v, str) else str(v))
    fields["row"] = row_number
    return doc_id_for(tab, fields, row_number), fields


def read_values(path):
    """Rows (header excluded) from a saved get_values result, or [] if the file is missing."""
    if not path or not os.path.exists(path):
        return []
    if os.path.isdir(path):
        return read_doc_dir(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    data = None
    try:
        data = json.loads(text)
    except Exception:
        i = text.find("{")
        while i != -1 and data is None:
            try:
                data = json.JSONDecoder().raw_decode(text[i:])[0]
            except Exception:
                i = text.find("{", i + 1)
    if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("type") == "text":
        return read_values_text(data[0].get("text", ""))
    if isinstance(data, dict) and "values" in data:
        return data["values"][1:]
    if isinstance(data, list):
        return data[1:]
    return []


def read_doc_dir(path):
    """Rows from a folder of na database documents (ArtifactData list with out_dir), in sheet-row order.
    Settings and facts live only in the database now; each document becomes the same row the old tab had."""
    docs = []
    for fp in sorted(glob.glob(os.path.join(path, "**", "*.json"), recursive=True)):
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        d = d.get("data", d) if isinstance(d, dict) else {}
        if isinstance(d, dict):
            docs.append(d)
    docs.sort(key=lambda d: (d.get("row") or 0))
    rows = []
    for d in docs:
        if "setting" in d:
            rows.append([d.get("setting", ""), d.get("value", ""), d.get("help", "")])
        elif "fact" in d:
            rows.append([d.get("fact", ""), d.get("value", ""), d.get("usedFor", "")])
        elif "jobId" in d or "title" in d:      # a feed document -> its New jobs row (A..S)
            rows.append(["" if d.get(name) is None else str(d.get(name)) for _, name in SCHEMA["Feed"]["columns"]])
    return rows


def read_values_text(text):
    try:
        return json.loads(text).get("values", [])[1:]
    except Exception:
        return []


def table(rows):
    """Key/value tabs (Search, Me) -> {lowercased key: value}."""
    out = {}
    for r in rows:
        if r and str(r[0]).strip():
            out[str(r[0]).strip().lower()] = str(r[1]).strip() if len(r) > 1 and r[1] is not None else ""
    return out


def split_list(value):
    return [x.strip() for x in re.split(r"[,;\n]", value or "") if x.strip()]


def want_from_sheet(search_rows, me_rows):
    """The Search and Me tabs -> one 'want' in the shape the shared code filter uses."""
    s, m = table(search_rows), table(me_rows)
    roles = split_list(s.get("roles", ""))
    places = split_list(s.get("places", "")) or ["United Kingdom"]
    countries = set()
    for p in places:
        f = fold(p)
        if "remote" in f and ("europe" in f or "eu" in f.split() or "emea" in f):
            countries.add("EU")
            continue
        if "remote" in f:
            countries.add("GB")
            continue
        countries |= place_to_countries(p)
    patterns = [p.strip().lower().replace("onsite", "on-site").replace("on site", "on-site") for p in split_list(s.get("work patterns", ""))] or ["remote", "hybrid", "on-site"]
    level = s.get("level", "entry").lower()
    try:
        max_years = int(float(s.get("max years asked", "")))
    except ValueError:
        max_years = None
    fluent = [x.split("(")[0].strip().lower() for x in split_list(m.get("fluent languages", "English"))]
    needs_visa = m.get("needs visa sponsorship", "no").strip().lower().startswith("y")
    return {"roles": roles, "countries": countries or {"GB"}, "places": places, "entryOnly": level.startswith("entry"),
            "patterns": patterns, "exclude": split_list(s.get("not these roles", "")), "maxYears": max_years,
            "needsVisa": needs_visa, "fluent": fluent or ["english"], "who": "sheet",
            "sources": [x.lower() for x in split_list(s.get("sources", "company sites, linkedin"))],
            "budget": float(s.get("daily budget (usd)", "0.75") or 0.75),
            "targets": split_list(s.get("target companies", ""))}


USER_SOURCES = ["company sites", "linkedin"]   # other users: the two sources that work best, nothing else
USER_BUDGET = 0.15                              # other users: at most ~$0.15 of Apify searching per person per day
RUN_CAP_USD = {"linkedin": 0.04, "indeed": 0.03, "glassdoor": 0.05, "wttj": 0.05, "reed": 0.05, "hirebase": 0.03}   # most one search may spend
TARGETS_MAX = 150                               # target companies checked per run
TARGETS_DAYS = 14                               # target companies: jobs posted in the last 2 weeks (only new ones are charged)
TARGETS_RESULTS = 30                            # at most 30 jobs from target companies per run (~$0.10)


def na_plan(search_rows, me_rows, settings=SETTINGS, user=False):
    w = want_from_sheet(search_rows, me_rows)
    if user:
        w["sources"] = [x for x in w["sources"] if x in USER_SOURCES] or list(USER_SOURCES)
        w["budget"] = min(w["budget"], USER_BUDGET)
    p = plan([w], settings)
    comp = p["companies_input"]
    comp["excludeKeywords"] = sorted(set(comp.get("excludeKeywords", [])) | {x.lower() for x in w["exclude"] if len(x) > 2})
    if "EU" in w["countries"]:
        comp["locations"] = sorted(set(comp["locations"]) | {"Remote (EU)", "Europe", "EMEA"})
    # company-sites cap from the daily budget (~$0.003 a job), leaving ~$0.12 for LinkedIn
    comp["maxResults"] = max(20, min(settings["companies_max_results"], int((w["budget"] - 0.12) / 0.003)))
    p["companies_budget_usd"] = round(comp["maxResults"] * 0.003 + 0.01, 2)
    # Collect runs several times a day: the company feed only returns (and charges for) jobs it hasn't delivered before
    comp["sinceLastRun"] = True
    # Target companies: their own career pages, checked for the same roles over a longer window
    p["targets_input"] = None
    if w.get("targets") and not user:
        p["targets_input"] = dict(comp, companies=w["targets"][:TARGETS_MAX], postedWithinDays=TARGETS_DAYS,
                                  maxResults=TARGETS_RESULTS, maxPerCompany=5, sinceLastRun=True)
        p["targets_budget_usd"] = round(TARGETS_RESULTS * 0.003 + 0.01, 2)
    if "company sites" not in " ".join(w["sources"]):
        p["companies_input"] = None
        p["targets_input"] = None
    if "linkedin" not in " ".join(w["sources"]):
        p["linkedin_inputs"] = []
    p["want"] = {k: (sorted(v) if isinstance(v, set) else v) for k, v in w.items()}
    p["runs"] = source_runs(p, w, table(me_rows))
    return p


FIELDS = {
    "companies": "title,company_name,ats,workplace_type,remote,salary_min,salary_max,salary_currency,years_experience_min,visa_sponsorship,posted_at,job_url,apply_url,locations,country_codes,description_text",
    "linkedin": "id,url,title,location,postedDate,companyName,workType,salary,description,applyUrl",
    "indeed": "jobUrl,title,employer.name,location.city,baseSalary.min,baseSalary.max,baseSalary.unitOfWork",
    "reed": "title,recruiter_name,location,location_type,is_remote,job_url,posted_date",
    "glassdoor": "title,employer.name,location.name,url,ageInDays",
    "wttj": "name,organizationName,offices.city,offices.country,remote,url,publishedAt",
    "hirebase": "jobTitle,companyName,location,locationType,applicationLink,datePosted,experienceLevel",
}


def source_runs(p, w, me):
    """Every Apify run for this collection, built from the roles in the Search tab.
    Inputs follow the actors' schemas as used by the PM Collect task."""
    srcs = " ".join(w["sources"])
    roles = p["roles"]                                  # core roles, redundant ones removed
    if not roles:
        return []
    home = split_list(me.get("home", ""))[:1]
    home = home[0] if home and fold(home[0]) not in ("uk", "united kingdom") else ""
    uk = "GB" in w["countries"]
    quoted = " OR ".join(f'"{r}"' for r in roles)
    no = ["senior", "lead", "principal", "head", "director", "staff"] if w["entryOnly"] else []
    no += [f'"{x}"' if " " in x else x for x in w["exclude"][:8]]
    runs = []

    def add(source, actor, inp, label, max_charge=None):
        runs.append({"source": source, "actor": actor, "input": inp, "fields": FIELDS[source],
                     "raw_file": f"raw/{source}_{sum(1 for r in runs if r['source'] == source) + 1}.txt", "label": label})
        max_charge = max_charge or RUN_CAP_USD.get(source)
        if max_charge:
            runs[-1]["max_charge_usd"] = max_charge

    if p.get("companies_input"):
        add("companies", "factpipe/ats-jobs-feed", p["companies_input"], "Company career sites", p.get("companies_budget_usd"))
    if p.get("targets_input"):
        add("companies", "factpipe/ats-jobs-feed", p["targets_input"], "Target companies' career pages", p.get("targets_budget_usd"))
    if "linkedin" in srcs:
        for li in p.get("linkedin_inputs", []):
            li = dict(li, keywords=f"({quoted})" + (f" NOT ({' OR '.join(no)})" if no else ""),
                      titleInclude=list(roles), titleExclude=[x.strip('"') for x in no])
            add("linkedin", "valig/linkedin-jobs-scraper", li, "LinkedIn " + li["location"])
        if uk and home:
            add("linkedin", "valig/linkedin-jobs-scraper", {"keywords": runs[-1]["input"]["keywords"] if runs and runs[-1]["source"] == "linkedin" else f"({quoted})",
                "location": f"{home}, United Kingdom", "datePosted": "r86400", "limit": 100, "easyApply": False, "under10Applicants": False,
                "titleInclude": list(roles), "titleExclude": [x.strip('"') for x in no]}, f"LinkedIn {home}")
    if uk and "indeed" in srcs:
        for loc in ["United Kingdom"] + ([home] if home else []):
            add("indeed", "valig/indeed-jobs-scraper", {"country": "uk", "title": quoted, "location": loc, "datePosted": "1", "limit": 150}, f"Indeed {loc}")
    if uk and "reed" in srcs:
        for r in roles[:2]:
            add("reed", "scrapersdelight/reed-jobs-scraper", {"keywords": r, "datePosted": "lastthreedays", "maxItems": 150, "fetchDetails": True}, f"Reed {r}")
        if home:
            add("reed", "scrapersdelight/reed-jobs-scraper", {"keywords": roles[0], "location": home, "proximity": 30, "datePosted": "lastweek", "maxItems": 100, "fetchDetails": True}, f"Reed {roles[0]} near {home}")
    if uk and "glassdoor" in srcs:
        for r in roles[:2]:
            add("glassdoor", "valig/glassdoor-jobs-scraper", {"keywords": r, "location": "United Kingdom", "daysOld": 1, "limit": 60}, f"Glassdoor {r}")
    if uk and ("welcome to the jungle" in srcs or "wttj" in srcs):
        for r in roles[:2]:
            add("wttj", "clearpath/welcome-to-the-jungle-jobs-api", {"query": r, "searchOnlyInJobTitle": True, "countryCode": "GB", "datePosted": "1", "maxItems": 60, "includeDetails": False}, f"Welcome to the Jungle {r}")
    if uk and "hirebase" in srcs:
        add("hirebase", "hirebase/remote-jobs", {"jobTitles": [r.title() if r.lower() != "apm" else "APM" for r in roles], "locations": ["United Kingdom"], "postedWithinDays": 3,
                                                  "maxResults": 150, "sortBy": "date_posted", "dedupeBy": "companyAndTitle"}, "hirebase")
    return runs


FACT_LABELS = [("pattern", None), ("yearsMin", "{}+ yrs"), ("visa", None), ("languages", None), ("agency", None), ("closing", "closes {}")]


def facts_text(f):
    bits = []
    if f.get("pattern") and f["pattern"] != "unknown":
        bits.append(f["pattern"].capitalize() if f["pattern"] != "on-site" else "On-site")
    if f.get("yearsMin") is not None:
        bits.append(f"{f['yearsMin']}+ yrs")
    if f.get("visa") is True:
        bits.append("visa sponsorship")
    if f.get("visa") is False:
        bits.append("no visa sponsorship")
    if f.get("languages"):
        bits.append("needs " + ", ".join(f["languages"]))
    if f.get("agency"):
        bits.append("agency")
    if f.get("closing"):
        bits.append("closes " + f["closing"])
    if f.get("level") == "entry":
        bits.append("entry level")
    return " · ".join(bits)


def na_build(search_rows, me_rows, feed_rows, raw_dir, out_dir, settings=SETTINGS, today=None, collection="feed"):
    found_at = today or now_iso()
    london_date = (datetime.fromisoformat(found_at.replace("Z", "+00:00")) if "T" in found_at else datetime.now(timezone.utc)).date().isoformat()
    w = want_from_sheet(search_rows, me_rows)
    report = {"foundAt": found_at, "fetched": {}, "dropped": {}, "added": 0, "already_in_sheet": 0, "duplicates": 0,
              "roles": plan([w], settings)["roles"]}

    def drop(rule):
        report["dropped"][rule] = report["dropped"].get(rule, 0) + 1

    raw = load_raw(raw_dir, report)
    all_rows = all_jobs_rows(raw, raw_dir, london_date)
    candidates = select_jobs(raw, [w], settings, report, drop, found_at)

    # already in the sheet: same Job ID, or same link
    have_ids, have_links = set(), set()
    id_col = [c[1] for c in SCHEMA["Feed"]["columns"]].index("jobId")
    link_col = [c[1] for c in SCHEMA["Feed"]["columns"]].index("link")
    for r in feed_rows:
        if len(r) > id_col and r[id_col]:
            have_ids.add(str(r[id_col]))
        if len(r) > link_col and r[link_col]:
            have_links.add(str(r[link_col]).strip())
    next_row = len(feed_rows) + 2  # header is row 1
    rows, db = [], []
    for did, (_, d) in sorted(candidates.items(), key=lambda kv: (kv[1][0], kv[1][1]["company"].lower())):
        if did in have_ids or d["url"].strip() in have_links:
            report["already_in_sheet"] += 1
            continue
        values = [london_date, d["site"], d["title"], d["company"], d["location"], d["salary"], d["url"],
                  facts_text(d["facts"]), sorted(d["roles"], key=lambda r: (len(r), r.lower()))[0] if d["roles"] else "",
                  "", "", "", "", "", "", "", "",
                  (d["postedAt"] or "")[:10], did]
        rows.append(values)
        _id, fields = row_to_doc("Feed", values, next_row)
        fields["advert"] = d["advert"][:6000]       # database only: lets the app show the advert without leaving na
        fields["factsData"] = d["facts"]
        fields["applyUrl"] = d.get("applyUrl", "")
        db.append({"op": "set", "collection": collection, "doc_id": _id, "data": fields})
        next_row += 1
    report["added"] = len(rows)
    summary = (f"Fetched {', '.join(f'{k} {v}' for k, v in report['fetched'].items())}; added {len(rows)} new; "
               f"{report['already_in_sheet']} already in the sheet; {report['duplicates']} duplicates")
    top = sorted(report["dropped"].items(), key=lambda kv: -kv[1])[:4]
    if top:
        summary += "; dropped: " + ", ".join(f"{k} {v}" for k, v in top)
    os.makedirs(out_dir, exist_ok=True)
    json.dump(rows, open(os.path.join(out_dir, "rows.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(db, open(os.path.join(out_dir, "db.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(all_rows, open(os.path.join(out_dir, "all_rows.json"), "w", encoding="utf-8"), ensure_ascii=False)
    report["all_jobs_rows"] = len(all_rows)
    json.dump(report, open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump([london_date + " " + found_at[11:16], "Collect", summary, ""],
              open(os.path.join(out_dir, "run_row.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return report, rows, db


ALL_JOBS_COLUMNS = ["Date found", "Search", "Title", "Company", "Location", "Salary", "Link", "Posted", "Processed", "Source"]
COUNTRY_NAMES = {"GB": "UK", "EU": "Europe"}


def all_jobs_rows(raw, raw_dir, london_date):
    """Every job this run fetched, before any filtering, as rows for the sheet's "All jobs" tab (the log of
    everything collected). Adzuna rows are already in that tab, and links already there are skipped."""
    have = set()
    for p in sorted(glob.glob(os.path.join(raw_dir, "adzuna*"))):
        for r in read_sheet_rows(p):
            if len(r) > 6 and r[6]:
                have.add(str(r[6]).strip())
    out = []
    for j in raw:
        url = (j.get("url") or "").strip()
        if not url or j.get("site") == "Adzuna" or url in have:
            continue
        have.add(url)
        out.append([london_date, COUNTRY_NAMES.get(j.get("country") or "", j.get("country") or ""), j.get("title", ""),
                    j.get("company", ""), j.get("location", ""), j.get("salaryText") or "Not stated", url,
                    (j.get("postedAt") or "")[:10], london_date, j.get("site", "")])
    return out


def _chunk(items, n, size):
    return items[(n - 1) * size: n * size]


def na_main(argv):
    ap = argparse.ArgumentParser(prog="na_engine.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("na-plan")
    p.add_argument("--search", required=True)
    p.add_argument("--me", required=True)
    p.add_argument("--out", default="plan.json")
    p.add_argument("--user", action="store_true", help="plan for another Sift user: company sites + LinkedIn only, small budget")
    b = sub.add_parser("na-build")
    b.add_argument("--search", required=True)
    b.add_argument("--me", required=True)
    b.add_argument("--feed", required=True)
    b.add_argument("--raw", required=True)
    b.add_argument("--out", default="out")
    b.add_argument("--collection", default="feed", help='database collection for the new jobs, e.g. "u/<user id>/feed"')
    for name, size in (("na-rows", 40), ("na-db", 50), ("na-all", 100)):
        c = sub.add_parser(name)
        c.add_argument("--out", default="out")
        c.add_argument("--n", type=int, required=True)
    s = sub.add_parser("na-schema")
    s.add_argument("--out", default="schema.json")
    a = ap.parse_args(argv)
    if a.cmd == "na-plan":
        pl = na_plan(read_values(a.search), read_values(a.me), user=a.user)
        json.dump(pl, open(a.out, "w", encoding="utf-8"), indent=1)
        w = pl["want"]
        print(f"roles: {', '.join(pl['roles']) or 'none'}; countries: {', '.join(w['countries'])}; "
              f"company sites: {'up to ' + str(pl['companies_input']['maxResults']) + ' jobs (~$' + str(pl['companies_budget_usd']) + ')' if pl['companies_input'] else 'off'}; "
              f"target companies: {str(len(pl['targets_input']['companies'])) + ' (up to ' + str(pl['targets_input']['maxResults']) + ' jobs, ~$' + str(pl['targets_budget_usd']) + ')' if pl.get('targets_input') else 'none'}; "
              f"{len(pl['runs'])} Apify runs: " + "; ".join(r["label"] for r in pl["runs"]) + f". Saved to {a.out}")
    elif a.cmd == "na-build":
        report, rows, db = na_build(read_values(a.search), read_values(a.me), read_values(a.feed), a.raw, a.out, collection=a.collection)
        print(json.load(open(os.path.join(a.out, "run_row.json")))[2])
        print(f"{len(rows)} rows -> {(len(rows) + 39) // 40} append chunk(s) (na-rows); {(len(db) + 49) // 50} database batch(es) (na-db); "
              f"{report['all_jobs_rows']} collected jobs -> {(report['all_jobs_rows'] + 99) // 100} All jobs chunk(s) (na-all)")
    elif a.cmd == "na-all":
        rows = json.load(open(os.path.join(a.out, "all_rows.json"), encoding="utf-8"))
        print(json.dumps(_chunk(rows, a.n, 100), ensure_ascii=False))
    elif a.cmd == "na-rows":
        rows = json.load(open(os.path.join(a.out, "rows.json"), encoding="utf-8"))
        print(json.dumps(_chunk(rows, a.n, 40), ensure_ascii=False))
    elif a.cmd == "na-db":
        db = json.load(open(os.path.join(a.out, "db.json"), encoding="utf-8"))
        # write each chunk to a file so the batch call can use file_path entries (keeps adverts out of the chat)
        chunk = _chunk(db, a.n, 50)
        folder = os.path.abspath(os.path.join(a.out, "dbdocs"))
        os.makedirs(folder, exist_ok=True)
        writes = []
        for w in chunk:
            path = os.path.join(folder, w["doc_id"] + ".json")
            json.dump(w["data"], open(path, "w", encoding="utf-8"), ensure_ascii=False)
            writes.append({"op": "set", "collection": w["collection"], "doc_id": w["doc_id"], "file_path": path})
        print(json.dumps(writes))
    elif a.cmd == "na-schema":
        json.dump(SCHEMA, open(a.out, "w", encoding="utf-8"), indent=1)
        print(f"wrote {a.out}")
    return 0
