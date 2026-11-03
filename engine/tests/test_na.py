import importlib.util
import json
import os
import shutil

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("na", os.path.join(HERE, "..", "na_engine.py"))
na = importlib.util.module_from_spec(spec)
spec.loader.exec_module(na)

SEARCH = [["Setting", "Value", "What it does"],
          ["Roles", "product manager, data analyst", ""],
          ["Not these roles", "product marketing, consultant", ""],
          ["Places", "United Kingdom, Amsterdam, Remote (Europe)", ""],
          ["Work patterns", "hybrid, on-site", ""],
          ["Level", "entry", ""],
          ["Max years asked", "2", ""],
          ["Sources", "company sites, LinkedIn", ""],
          ["Daily budget (USD)", "0.5", ""]]
ME = [["Fact", "Value", "Used for"], ["Fluent languages", "English, Arabic", ""], ["Needs visa sponsorship", "Yes", ""]]


def vals(rows):
    return {"range": "x", "values": rows}


@pytest.fixture
def files(tmp_path):
    shutil.copytree(os.path.join(HERE, "fx", "raw"), tmp_path / "raw")
    for name, rows in (("search", SEARCH), ("me", ME), ("feed", [[c[0] for c in na.SCHEMA["Feed"]["columns"]]])):
        json.dump(vals(rows), open(tmp_path / f"{name}.json", "w"))
    return tmp_path


def test_want_from_sheet():
    w = na.want_from_sheet(SEARCH[1:], ME[1:])
    assert w["countries"] == {"GB", "NL", "EU"}
    assert w["patterns"] == ["hybrid", "on-site"] and w["maxYears"] == 2 and w["needsVisa"] is True
    assert w["fluent"] == ["english", "arabic"] and w["exclude"] == ["product marketing", "consultant"]


def test_plan_budget_and_excludes():
    p = na.na_plan(SEARCH[1:], ME[1:])
    c = p["companies_input"]
    assert c["maxResults"] == int((0.5 - 0.12) / 0.003)
    assert "product marketing" in c["excludeKeywords"] and "senior" in c["excludeKeywords"]
    assert "Remote (EU)" in c["locations"] and "NL" in c["locations"]
    assert [r["location"] for r in p["linkedin_inputs"]] == ["United Kingdom", "Netherlands"]


def test_sources_switch_off():
    s = [r[:] for r in SEARCH]
    s[7][1] = "LinkedIn"
    p = na.na_plan(s[1:], ME[1:])
    assert p["companies_input"] is None and p["linkedin_inputs"]


def test_build_rows_and_personal_rules(files):
    extra = {"title": "Graduate Product Manager", "company_name": "NoSponsor Ltd", "ats": "lever", "workplace_type": "hybrid",
             "posted_at": "2026-10-26T00:00:00Z", "job_url": "https://jobs.lever.co/nosponsor/1", "locations": ["Leeds"],
             "country_codes": ["GB"], "description_text": "We are unable to offer visa sponsorship. " + "Own the roadmap and iterate. " * 20}
    json.dump({"items": [extra]}, open(files / "raw" / "companies_2.json", "w"))
    report, rows, db = na.na_build(na.read_values(str(files / "search.json")), na.read_values(str(files / "me.json")),
                                   na.read_values(str(files / "feed.json")), str(files / "raw"), str(files / "out"),
                                   today="2026-10-27T06:40:00Z")
    d = report["dropped"]
    assert d["says it can't sponsor a visa, and you need one"] == 1        # NoSponsor Ltd (this user needs a visa)
    assert d["needs a language you're not fluent in"] == 1                  # Picnic needs Dutch
    titles = {r[2] for r in rows}
    assert "Junior Data Analyst" not in titles
    assert all(len(r) == len(na.SCHEMA["Feed"]["columns"]) == 20 for r in rows)   # A..T, no Salary
    assert rows[0][0] == "2026-10-27" and rows[0][8] == ""                   # Decision empty for review
    # database docs mirror the row exactly, plus app-only extras
    for r, w in zip(rows, db):
        assert w["doc_id"] == r[17]
        cols = [c[1] for c in na.SCHEMA["Feed"]["columns"]]
        assert all(w["data"][k] == r[i] for i, k in enumerate(cols))
        assert w["data"]["row"] >= 2 and "advert" in w["data"]


def test_existing_rows_not_added_twice(files):
    args = (na.read_values(str(files / "search.json")), na.read_values(str(files / "me.json")))
    _, rows, _ = na.na_build(*args, na.read_values(str(files / "feed.json")), str(files / "raw"), str(files / "o1"))
    feed = [[c[0] for c in na.SCHEMA["Feed"]["columns"]]] + rows
    json.dump(vals(feed), open(files / "feed2.json", "w"))
    rep, rows2, db2 = na.na_build(*args, na.read_values(str(files / "feed2.json")), str(files / "raw"), str(files / "o2"))
    assert rows2 == [] and rep["already_in_sheet"] == len(rows)


def test_doc_ids_match_app_rule():
    assert na.doc_id_for("Search", {"setting": "Max years asked"}, 7) == "max-years-asked"
    assert na.doc_id_for("Me", {"fact": "Needs visa sponsorship"}, 5) == "needs-visa-sponsorship"
    assert na.doc_id_for("Runs", {}, 12) == "r000012"
    assert na.doc_id_for("Feed", {"jobId": "jabc123"}, 3) == "jabc123"
    assert na.doc_id_for("Feed", {"jobId": ""}, 3) == "row000003"


def test_read_values_variants(tmp_path):
    p = tmp_path / "v.txt"
    p.write_text('[{"type":"text","text":"{\\"range\\":\\"A\\",\\"values\\":[[\\"h\\"],[\\"a\\",\\"b\\"]]}"}]')
    assert na.read_values(str(p)) == [["a", "b"]]
    p.write_text('Result: {"range":"A","values":[["h"],["x"]]} trailing')
    assert na.read_values(str(p)) == [["x"]]
    assert na.read_values(str(tmp_path / "missing.json")) == []


def test_uk_board_sources(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    json.dump({"items": [{"jobUrl": "https://uk.indeed.com/viewjob?jk=1", "title": "Junior Product Manager", "employer.name": "Acme",
                          "location.city": "Loughborough", "baseSalary.min": 30000, "baseSalary.max": 35000, "baseSalary.unitOfWork": "YEAR"}]}, open(raw / "indeed_1.txt", "w"))
    json.dump({"items": [{"title": "Product Manager", "recruiter_name": "Hays", "location": "Nottingham", "location_type": "hybrid",
                          "is_remote": False, "job_url": "https://www.reed.co.uk/jobs/1", "posted_date": "27/10/2026"}]}, open(raw / "reed_1.txt", "w"))
    json.dump({"items": [{"title": "Associate Product Manager", "employer": {"name": "Beta"}, "location": {"name": "Birmingham, England"}, "url": "https://glassdoor.co.uk/1"}]}, open(raw / "glassdoor_1.txt", "w"))
    json.dump({"items": [{"name": "Product Manager", "organizationName": "Gamma", "offices": [{"city": "London", "country": "United Kingdom"}], "remote": "partial", "url": "https://wttj/1", "publishedAt": "2026-10-26T10:00:00Z"}]}, open(raw / "wttj_1.txt", "w"))
    json.dump({"items": [{"jobTitle": "Product Manager", "companyName": "Delta", "location": "Remote, UK", "locationType": "remote", "applicationLink": "https://delta/1", "datePosted": "2026-10-26"}]}, open(raw / "hirebase_1.txt", "w"))
    json.dump({"range": "All jobs!A1:J9", "values": [["A"], ["2026-10-27", "UK", "Graduate Product Manager", "Epsilon", "Market Harborough", "Not stated", "https://adzuna/1", "", "", "Adzuna"],
                                                       ["2026-10-27", "UK", "Product Manager", "Done Ltd", "Leeds", "Not stated", "https://adzuna/2", "", "2026-10-26", "Adzuna"]]}, open(raw / "adzuna_1.json", "w"))
    s = [r[:] for r in SEARCH]; s[4][1] = "hybrid, remote"
    rep, rows, db = na.na_build(s[1:], [["Fluent languages", "English"]], [], str(raw), str(tmp_path / "out"))
    assert rows == [] and rep["short_ads"] == 6       # no ad text: all held for the cloud reader on the first pass
    rep, rows, db = na.na_build(s[1:], [["Fluent languages", "English"]], [], str(raw), str(tmp_path / "out"),
                                settings=dict(na.SETTINGS, after_reader=True))
    assert all(r[8] == "Check manually" and r[9] == na.CHECK_MANUALLY_REASON for r in rows)
    got = {(r[1], r[3]) for r in rows}
    assert got == {("Indeed", "Acme"), ("Reed", "Hays"), ("Glassdoor", "Beta"), ("Welcome to the Jungle", "Gamma"), ("hirebase", "Delta"), ("Adzuna", "Epsilon")}
    by = {r[3]: r for r in rows}
    assert "£30,000 - £35,000/year" not in by["Acme"] and by["Hays"][6].startswith("Hybrid") and "agency" in by["Hays"][6]   # no Salary column in New jobs
    assert rep["fetched"]["Adzuna (sheet backup)"] == 1   # no Apify Adzuna results, so the sheet script is used; the processed row is skipped


def test_all_jobs_rows(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    json.dump({"items": [{"jobUrl": "https://uk.indeed.com/viewjob?jk=1", "title": "Junior Product Manager", "employer.name": "Acme", "location.city": "Leeds"},
                         {"jobUrl": "https://uk.indeed.com/viewjob?jk=2", "title": "Software Engineer", "employer.name": "Beta", "location.city": "Leeds"}]}, open(raw / "indeed_1.txt", "w"))
    json.dump({"range": "All jobs!A1:J9", "values": [["A"], ["2026-10-27", "UK", "Old", "Old Co", "UK", "Not stated", "https://uk.indeed.com/viewjob?jk=2", "", "2026-10-27", "Indeed"],
                                                       ["2026-10-27", "UK", "PM", "Z", "UK", "Not stated", "https://adzuna/9", "", "", "Adzuna"]]}, open(raw / "adzuna_1.json", "w"))
    rep, rows, db = na.na_build(SEARCH[1:], ME[1:], [], str(raw), str(tmp_path / "out"), today="2026-10-28T09:00:00Z")
    allr = json.load(open(tmp_path / "out" / "all_rows.json"))
    # every fetched job (even ones the filters drop) except links already in All jobs and Adzuna's own rows
    assert [r[6] for r in allr] == ["https://uk.indeed.com/viewjob?jk=1"]
    assert allr[0][0] == "2026-10-28" and allr[0][9] == "Indeed" and len(allr[0]) == len(na.ALL_JOBS_COLUMNS)


def test_settings_from_database_folder(tmp_path):
    d = tmp_path / "db" / "search"; d.mkdir(parents=True)
    for i, r in enumerate(SEARCH[1:], 2):
        json.dump({"data": {"setting": r[0], "value": r[1], "help": r[2], "row": i}}, open(d / f"s{i}.json", "w"))
    assert na.read_values(str(d)) == [r[:3] for r in SEARCH[1:]]
    p = na.na_plan(na.read_values(str(d)), ME[1:])
    assert p["companies_input"]["maxResults"] == int((0.5 - 0.12) / 0.003)


def test_user_plan_is_capped():
    search = [r[:] for r in SEARCH[1:]]
    for r in search:
        if r[0] == "Sources":
            r[1] = "company sites, linkedin, indeed, reed, glassdoor"
        if r[0] == "Daily budget (USD)":
            r[1] = "5"
    p = na.na_plan(search, ME[1:], user=True)
    assert {r["source"] for r in p["runs"]} <= {"companies", "linkedin"}
    assert p["companies_budget_usd"] <= na.USER_BUDGET + 0.02


def test_feed_from_database_folder_and_user_collection(tmp_path):
    d = tmp_path / "feed"; d.mkdir()
    json.dump({"data": {"jobId": "jabc", "title": "PM", "company": "X", "link": "https://x/1", "row": 2}}, open(d / "jabc.json", "w"))
    rows = na.read_values(str(d))
    cols = [c[1] for c in na.SCHEMA["Feed"]["columns"]]
    assert rows[0][cols.index("jobId")] == "jabc" and rows[0][cols.index("link")] == "https://x/1"


def test_target_companies_get_their_own_capped_run():
    search = [r[:] for r in SEARCH[1:]] + [["Target companies", "Monzo, Wise, Deliveroo", "", 11]]
    p = na.na_plan(search, ME[1:], uk_hour=8)
    comp = [r for r in p["runs"] if r["source"] == "companies"]
    assert len(comp) == 2 and comp[0]["raw_file"] != comp[1]["raw_file"]
    t = comp[1]["input"]
    assert t["companies"] == ["Monzo", "Wise", "Deliveroo"] and t["sinceLastRun"] and t["postedWithinDays"] == na.TARGETS_DAYS
    assert t["keywords"] == comp[0]["input"]["keywords"] and t["maxResults"] == na.TARGETS_RESULTS
    assert comp[0]["input"]["sinceLastRun"] and all(r["max_charge_usd"] > 0 for r in comp)
    # other users never get the target-companies run
    assert not [r for r in na.na_plan(search, ME[1:], user=True)["runs"] if "companies" in r["input"]]


def test_no_target_companies_means_one_company_run():
    p = na.na_plan(SEARCH[1:], ME[1:], uk_hour=8)
    assert len([r for r in p["runs"] if r["source"] == "companies"]) == 1 and p["targets_input"] is None


def test_every_paid_run_has_a_spending_cap():
    search = [r[:] for r in SEARCH[1:]]
    for r in search:
        if r[0] == "Sources":
            r[1] = "company sites, linkedin, indeed, reed, glassdoor, welcome to the jungle, hirebase"
    search.append(["Places", "United Kingdom", ""])
    runs = na.na_plan(search, [["Home", "Leicester", ""]] + ME[1:])["runs"]
    assert runs and all(r.get("max_charge_usd", 0) > 0 for r in runs)
    li = [r for r in runs if r["source"] == "linkedin"]
    assert li and all(r["input"]["titleInclude"] and "senior" in r["input"]["titleExclude"] for r in li)


def test_full_ads_saved_once_for_later_steps(files):
    report, rows, _ = na.na_build(na.read_values(str(files / "search.json")), na.read_values(str(files / "me.json")),
                                  na.read_values(str(files / "feed.json")), str(files / "raw"), str(files / "out"),
                                  today="2026-10-27T06:40:00Z")
    ads = json.load(open(files / "out" / "ads.json"))
    assert ads and report["ads_saved"] == len(ads) <= len(rows)
    ids = {r[17] for r in rows}
    for ad in ads:
        assert ad["jobId"] in ids and ad["chars"] == len(ad["text"]) >= na.AD_MIN_CHARS
        assert "<" not in ad["text"][:200] and ad["savedBy"] == "Collect"
        row = next(r for r in rows if r[17] == ad["jobId"])
        assert len(ad["text"]) >= len(row[18].rstrip(" …"))      # the saved ad is the whole ad, not the 800-character excerpt
    # na-ads prints batch writes that read each ad from its own file
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        na.na_main(["na-ads", "--out", str(files / "out"), "--n", "1"])
    writes = json.loads(buf.getvalue())
    assert len(writes) == min(len(ads), na.ADS_PER_BATCH)
    for w in writes:
        assert w["collection"] == "ads" and w["op"] == "set" and "data" not in w
        assert json.load(open(w["file_path"]))["jobId"] == w["doc_id"]


def test_no_ad_saved_without_usable_text():
    assert na.ad_doc("j1", {"advert": "", "noAdvert": True}, "t") is None
    assert na.ad_doc("j1", {"advert": "Short."}, "t") is None
    ad = na.ad_doc("j1", {"advert": "<p>Own the roadmap.</p>" * 20, "title": "PM", "url": "u"}, "t")
    assert ad and "<p>" not in ad["text"]


def test_short_ads_go_to_reader_then_check_manually(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    long_ad = "Own the product roadmap, run discovery with users and work with engineers. " * 6
    json.dump({"items": [
        {"title": "Graduate Product Manager", "company": "Alpha", "location": "London", "jobUrl": "https://www.adzuna.co.uk/details/1",
         "description": "Short snippet ...", "descriptionSnippet": "Short snippet ..."},
        {"title": "Associate Product Manager", "company": "Bravo", "location": "Leeds", "jobUrl": "https://bravo.example/jobs/2",
         "description": "Tiny.", "descriptionSnippet": "Tiny."},
        {"title": "Junior Product Manager", "company": "Charlie", "location": "London", "jobUrl": "https://charlie.example/jobs/3",
         "description": long_ad, "descriptionSnippet": "Own the"}]}, open(raw / "adzunaapi_1.txt", "w"))
    s = [r[:] for r in SEARCH]; s[4][1] = "hybrid, remote, on-site"
    me = [["Fluent languages", "English"]]
    rep, rows, _ = na.na_build(s[1:], me, [], str(raw), str(tmp_path / "out"))
    assert [r[3] for r in rows] == ["Charlie"] and rep["short_ads"] == 2
    short = json.load(open(tmp_path / "out" / "short.json"))
    spec = na.reader_run(short)
    assert [u["url"] for u in spec["input"]["startUrls"]] == ["https://bravo.example/jobs/2"]   # Adzuna pages are skipped
    assert spec["call_options"]["timeout"] == 300 and spec["max_charge_usd"]
    json.dump({"items": [{"url": "https://bravo.example/jobs/2/", "text": long_ad.replace("roadmap", "backlog"), "crawl.httpStatusCode": 200},
                         {"url": "https://www.adzuna.co.uk/details/1", "text": "Human Verification. Let's confirm you are human. " * 10}]},
              open(raw / "reader_1.txt", "w"))
    rep, rows, _ = na.na_build(s[1:], me, [], str(raw), str(tmp_path / "out"), settings=dict(na.SETTINGS, after_reader=True))
    by = {r[3]: r for r in rows}
    assert rep["reader_filled"] == 1 and by["Bravo"][8] == "" and "backlog" in json.dumps(json.load(open(tmp_path / "out" / "ads.json")))
    assert by["Alpha"][8] == "Check manually" and by["Charlie"][8] == ""      # the human-check page was never used as the ad


def test_new_sources_planned():
    s = [r[:] for r in SEARCH]; s[7][1] = "company sites, LinkedIn, Indeed, Reed, Welcome to the Jungle, Adzuna, TargetJobs"
    p = na.na_plan(s[1:], ME[1:])
    by = {r["source"]: r for r in p["runs"]}
    assert by["adzunaapi"]["input"]["fetchDescription"] is True and by["adzunaapi"]["call_options"]["memory"] == 512
    assert by["wttj"]["input"]["includeDetails"] is True and "description" in by["wttj"]["fields"]
    assert "description.text" in by["indeed"]["fields"] and "description_text" in by["reed"]["fields"]
    morning = na.uk_hour() < na.MORNING_BEFORE_UK_HOUR
    assert (len([r for r in p["runs"] if r["source"] == "targetjobs"]) == 1) == morning
    assert (len([r for r in p["runs"] if r["source"] == "companies"]) > 0) == morning


def test_once_a_day_searches_only_in_the_morning_run():
    s = [r[:] for r in SEARCH]; s[7][1] = "company sites, LinkedIn, TargetJobs"
    w = na.want_from_sheet(s[1:], ME[1:])
    base = na.na_plan(s[1:], ME[1:])
    for hour, expect in ((8, True), (11, False)):
        runs = na.source_runs(dict(base, uk_hour=hour), w, na.table(ME[1:]))
        srcs = {r["source"] for r in runs}
        assert ("companies" in srcs) == expect and ("targetjobs" in srcs) == expect and "linkedin" in srcs


def test_run_usage_counts_each_reply_once(tmp_path):
    lines = [
        {"message": {"role": "user", "content": "go"}},
        {"message": {"role": "assistant", "id": "m1", "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 5},
                     "content": [{"type": "text", "text": "x"}]}},
        {"message": {"role": "assistant", "id": "m1", "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 5},
                     "content": [{"type": "tool_use", "name": "Bash"}]}},
        {"message": {"role": "assistant", "id": "m2", "usage": {"input_tokens": 1, "cache_read_input_tokens": 2000, "output_tokens": 7},
                     "content": [{"type": "tool_use"}, {"type": "tool_use"}]}},
        "not json"]
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps(x) if isinstance(x, dict) else x for x in lines))
    u = na.run_usage(str(p))
    assert u == {"tokens_in": 3111, "cached": 3000, "tokens_out": 12, "tool_calls": 3, "steps": 2}
