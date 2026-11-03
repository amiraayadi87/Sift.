import importlib.util
import json
import os
import shutil

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ff", os.path.join(HERE, "..", "na_engine.py"))
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)


@pytest.fixture
def run(tmp_path):
    shutil.copytree(os.path.join(HERE, "fx"), tmp_path / "fx")
    out = tmp_path / "out"
    report, batches = ff.build(str(tmp_path / "fx/state"), str(tmp_path / "fx/raw"), str(out), today="2026-10-27T07:00:00Z")
    docs = {os.path.splitext(f)[0]: json.load(open(out / "docs" / f)) for f in os.listdir(out / "docs")}
    return report, batches, docs, out


def titles(docs):
    return sorted((d["title"], d["company"]) for d in docs.values())


def test_filters_and_dedup(run):
    report, batches, docs, _ = run
    assert titles(docs) == sorted([
        ("Product Manager", "Nous"),                         # once, even though on company site AND LinkedIn
        ("Associate Product Manager", "Hays"),
        ("Product Manager (Operations)", "Lendable"),
        ("Junior Data Analyst", "Picnic"),
    ])
    d = report["dropped"]
    assert d["asks for 5+ years, everyone matching wants entry level"] == 2   # Constantinople, Hulcan
    assert d["asks for a fee or ID documents (likely scam)"] == 1
    assert d["senior title, everyone matching wants entry level"] == 1       # Barclays AVP
    assert d["country nobody asked for"] == 1                                # Berlin: nobody asked for DE
    assert d["not UK or Europe"] == 1                                         # New York
    assert "advert text too short to judge" not in d and len(report["short"]) == 1   # held for the cloud reader, not dropped
    assert report["duplicates"] == 1


def test_company_site_wins_over_linkedin(run):
    _, _, docs, _ = run
    nous = [d for d in docs.values() if d["company"] == "Nous"][0]
    assert nous["site"] == "Company site (Ashby)" and nous["facts"]["visa"] is True


def test_facts(run):
    _, _, docs, _ = run
    by = {d["company"]: d for d in docs.values()}
    assert by["Hays"]["facts"]["agency"] is True and by["Hays"]["salary"] == "£35,000 – £40,000"
    assert by["Picnic"]["facts"] == {**by["Picnic"]["facts"], "pattern": "on-site", "yearsMin": 1, "languages": ["Dutch"], "country": "NL"}
    assert by["Lendable"]["facts"]["salaryMin"] == 55000
    for d in docs.values():  # fields Fewer reads
        assert d["title"] and d["advert"] and d["url"] and d["foundAt"] == "2026-10-27T07:00:00Z" and d["roles"]


def test_manifest_deletes_old_with_version(run):
    _, batches, _, out = run
    flat = [w for b in batches for w in b]
    dele = [w for w in flat if w["op"] == "delete"]
    assert dele == [{"op": "delete", "collection": "feed", "doc_id": "jold", "if_version": 7}]
    assert all(os.path.exists(w["file_path"]) for w in flat if w["op"] == "set")
    assert all(len(b) <= 50 for b in batches)
    status = json.load(open(out / "status.json"))
    assert status["added"] == 4 and status["feedSize"] == 4


def test_existing_jobs_not_rewritten(tmp_path):
    shutil.copytree(os.path.join(HERE, "fx"), tmp_path / "fx")
    out1 = tmp_path / "o1"
    ff.build(str(tmp_path / "fx/state"), str(tmp_path / "fx/raw"), str(out1), today="2026-10-27T07:00:00Z")
    for f in os.listdir(out1 / "docs"):  # pretend they were uploaded (ArtifactData out_dir layout)
        os.makedirs(tmp_path / "fx/state/feed/feed", exist_ok=True)
        json.dump({"id": f[:-5], "data": json.load(open(out1 / "docs" / f)), "version": 1}, open(tmp_path / "fx/state/feed/feed" / f, "w"))
    report, batches = ff.build(str(tmp_path / "fx/state"), str(tmp_path / "fx/raw"), str(tmp_path / "o2"), today="2026-10-28T07:00:00Z")
    assert report["added"] == 0 and report["kept_existing"] == 4


def test_plan():
    wants = ff.gather_wants(os.path.join(HERE, "fx/state"))
    p = ff.plan(wants)
    assert p["countries"] == ["GB", "NL"]
    assert [r["location"] for r in p["linkedin_inputs"]] == ["United Kingdom", "Netherlands"]
    assert "senior" in p["companies_input"]["excludeKeywords"]


@pytest.mark.parametrize("title,role,ok", [
    ("Junior Data Analyst", "Data Analyst", True),
    ("Data & Insights Analyst", "Data Analyst", True),
    ("Graduate Product Manager", "product manager", True),
    ("Product Marketing Manager", "product manager", False),
    ("Analyst, Data", "data analyst", True),
    ("Product Manager", "Product Management", True),
    ("Associate Product Manager", "Junior Product Management", True),
    ("Product Marketing Manager", "Product Management", False),
    ("Data Engineer", "Data Analyst", False),
    ("Analytics Engineer", "Data Analytics", False),
])
def test_role_matches(title, role, ok):
    assert ff.role_matches(title, role) is ok


def test_plan_terms_for_management():
    w = [{"roles": ["Product Management", "Junior Product Management"], "countries": {"GB"}, "entryOnly": True,
          "patterns": ["hybrid"], "places": ["Leicester"], "who": "u"}]
    assert ff.plan(w)["roles"] == ["product management", "product manager"]
    w[0]["roles"] = ["graduate data analyst", "junior data analyst"]
    assert ff.plan(w)["roles"] == ["data analyst"]


def test_load_items_variants(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text('[{"type":"text","text":"{\\"items\\":[{\\"a\\":1}]}"}]')
    assert ff.load_items(str(p)) == [{"a": 1}]
    p.write_text('noise before {"items":[{"b":2}],"itemCount":1} after')
    assert ff.load_items(str(p)) == [{"b": 2}]
