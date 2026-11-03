#!/usr/bin/env python3
"""Fewer daily feed collector (single file, standard library only).
Built from JobRadar (location, agency and text helpers) + the collector. Do not edit by hand:
regenerate with make_single_file.py."""
import hashlib
import html as _html
import re
import unicodedata

# ---------------------------------------------------------------- location (from JobRadar geo.py)


UK = {"GB"}
EU27 = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
        "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
OTHER_EUROPE = {"NO", "IS", "LI", "CH", "RS", "UA", "MD", "AL", "BA", "ME", "MK", "XK", "AD", "MC", "SM", "GI", "IM", "JE", "GG"}
EUROPE = UK | EU27 | OTHER_EUROPE

# names -> ISO code (lowercase, accents stripped). English + local names.
COUNTRY_NAMES = {
    "united kingdom": "GB", "uk": "GB", "u.k.": "GB", "great britain": "GB", "britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB", "gb": "GB", "gbr": "GB",
    "ireland": "IE", "eire": "IE", "republic of ireland": "IE",
    "germany": "DE", "deutschland": "DE", "france": "FR", "netherlands": "NL", "the netherlands": "NL",
    "nederland": "NL", "holland": "NL", "belgium": "BE", "belgie": "BE", "belgique": "BE",
    "luxembourg": "LU", "spain": "ES", "espana": "ES", "portugal": "PT", "italy": "IT", "italia": "IT",
    "austria": "AT", "osterreich": "AT", "switzerland": "CH", "schweiz": "CH", "suisse": "CH", "svizzera": "CH",
    "sweden": "SE", "sverige": "SE", "norway": "NO", "norge": "NO", "denmark": "DK", "danmark": "DK",
    "finland": "FI", "suomi": "FI", "iceland": "IS", "island": "IS", "poland": "PL", "polska": "PL",
    "czech republic": "CZ", "czechia": "CZ", "cesko": "CZ", "ceska republika": "CZ", "slovakia": "SK",
    "slovensko": "SK", "hungary": "HU", "magyarorszag": "HU", "romania": "RO", "bulgaria": "BG",
    "greece": "GR", "croatia": "HR", "hrvatska": "HR", "slovenia": "SI", "slovenija": "SI",
    "estonia": "EE", "eesti": "EE", "latvia": "LV", "latvija": "LV", "lithuania": "LT", "lietuva": "LT",
    "cyprus": "CY", "malta": "MT", "liechtenstein": "LI", "serbia": "RS", "ukraine": "UA",
    "moldova": "MD", "albania": "AL", "bosnia": "BA", "montenegro": "ME", "north macedonia": "MK",
    "kosovo": "XK", "andorra": "AD", "monaco": "MC", "gibraltar": "GI", "isle of man": "IM",
    "guernsey": "GG",
}

# Major cities -> ISO code. Covers the big job markets; extend freely.
CITIES = {
    # UK
    "london": "GB", "manchester": "GB", "birmingham": "GB", "leeds": "GB", "glasgow": "GB",
    "edinburgh": "GB", "bristol": "GB", "cardiff": "GB", "belfast": "GB", "liverpool": "GB",
    "newcastle": "GB", "newcastle upon tyne": "GB", "sheffield": "GB", "nottingham": "GB",
    "cambridge": "GB", "oxford": "GB", "reading": "GB", "brighton": "GB", "southampton": "GB",
    "leicester": "GB", "coventry": "GB", "milton keynes": "GB", "aberdeen": "GB", "dundee": "GB",
    "york": "GB", "bath": "GB", "exeter": "GB", "norwich": "GB", "swansea": "GB", "plymouth": "GB",
    "portsmouth": "GB", "guildford": "GB", "slough": "GB", "watford": "GB", "croydon": "GB",
    "stockport": "GB", "salford": "GB", "bournemouth": "GB", "derby": "GB", "stoke": "GB",
    "chester": "GB", "warrington": "GB", "basingstoke": "GB", "farnborough": "GB", "crawley": "GB",
    "canary wharf": "GB", "city of london": "GB", "harrogate": "GB", "inverness": "GB", "stirling": "GB",
    # Ireland
    "dublin": "IE", "cork": "IE", "galway": "IE", "limerick": "IE",
    # DACH
    "berlin": "DE", "munich": "DE", "munchen": "DE", "hamburg": "DE", "frankfurt": "DE",
    "cologne": "DE", "koln": "DE", "stuttgart": "DE", "dusseldorf": "DE", "leipzig": "DE",
    "dresden": "DE", "hanover": "DE", "hannover": "DE", "nuremberg": "DE", "nurnberg": "DE",
    "bonn": "DE", "karlsruhe": "DE", "essen": "DE", "dortmund": "DE", "bremen": "DE", "mannheim": "DE",
    "vienna": "AT", "wien": "AT", "graz": "AT", "linz": "AT", "salzburg": "AT", "innsbruck": "AT",
    "zurich": "CH", "geneva": "CH", "geneve": "CH", "basel": "CH", "bern": "CH", "lausanne": "CH", "zug": "CH",
    # Benelux
    "amsterdam": "NL", "rotterdam": "NL", "the hague": "NL", "den haag": "NL", "utrecht": "NL",
    "eindhoven": "NL", "groningen": "NL", "delft": "NL", "leiden": "NL",
    "brussels": "BE", "bruxelles": "BE", "brussel": "BE", "antwerp": "BE", "antwerpen": "BE",
    "ghent": "BE", "gent": "BE", "leuven": "BE",
    # France
    "paris": "FR", "lyon": "FR", "marseille": "FR", "toulouse": "FR", "nantes": "FR", "lille": "FR",
    "bordeaux": "FR", "nice": "FR", "montpellier": "FR", "rennes": "FR", "grenoble": "FR", "strasbourg": "FR",
    "sophia antipolis": "FR",
    # Iberia
    "madrid": "ES", "barcelona": "ES", "valencia": "ES", "seville": "ES", "sevilla": "ES", "malaga": "ES",
    "bilbao": "ES", "zaragoza": "ES", "lisbon": "PT", "lisboa": "PT", "porto": "PT", "braga": "PT",
    # Italy
    "milan": "IT", "milano": "IT", "rome": "IT", "roma": "IT", "turin": "IT", "torino": "IT",
    "bologna": "IT", "florence": "IT", "firenze": "IT", "naples": "IT", "napoli": "IT",
    # Nordics
    "stockholm": "SE", "gothenburg": "SE", "goteborg": "SE", "malmo": "SE", "uppsala": "SE",
    "oslo": "NO", "bergen": "NO", "trondheim": "NO", "copenhagen": "DK", "kobenhavn": "DK", "aarhus": "DK",
    "helsinki": "FI", "espoo": "FI", "tampere": "FI", "reykjavik": "IS",
    # CEE / Baltics / SEE
    "warsaw": "PL", "warszawa": "PL", "krakow": "PL", "wroclaw": "PL", "gdansk": "PL", "poznan": "PL", "lodz": "PL", "katowice": "PL",
    "prague": "CZ", "praha": "CZ", "brno": "CZ", "bratislava": "SK", "budapest": "HU",
    "bucharest": "RO", "bucuresti": "RO", "cluj": "RO", "cluj-napoca": "RO", "iasi": "RO", "timisoara": "RO",
    "sofia": "BG", "plovdiv": "BG", "athens": "GR", "thessaloniki": "GR", "zagreb": "HR", "split": "HR",
    "ljubljana": "SI", "tallinn": "EE", "tartu": "EE", "riga": "LV", "vilnius": "LT", "kaunas": "LT",
    "belgrade": "RS", "novi sad": "RS", "kyiv": "UA", "kiev": "UA", "lviv": "UA", "chisinau": "MD",
    "limassol": "CY", "nicosia": "CY", "valletta": "MT", "luxembourg city": "LU", "sarajevo": "BA", "tirana": "AL",
}

# Europe-wide remote wording
REGION_WORDS = ["europe", "european union", "emea", "eu", "eea", "cet", "cest", "dach", "benelux",
                "nordics", "nordic", "scandinavia", "baltics", "cee", "western europe", "eastern europe"]

# "London, ON" / "Cambridge, MA" / "Birmingham, AL" are not in Europe
# (deliberately leaves out codes that clash with European ones: DE, NL, ME, MT, SK, AL is kept
#  because "Birmingham, AL" is far more common than an Albanian city written that way)
NON_EU_SUFFIX = {"al", "ak", "az", "ar", "ca", "co", "ct", "fl", "ga", "hi", "id", "il", "in", "ia", "ks",
                 "ky", "la", "md", "ma", "mi", "mn", "ms", "mo", "ne", "nv", "nh", "nj", "nm", "ny",
                 "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
                 "wi", "wy", "dc", "on", "qc", "bc", "ab", "mb", "ns", "nb", "pe", "nsw", "vic", "qld",
                 "usa", "us", "united states", "canada", "australia", "texas", "ontario", "kentucky", "alabama",
                 "massachusetts", "new hampshire", "connecticut", "virginia", "maryland", "south carolina"}
NON_EU_WORDS = ["united states", "usa", "u.s.", "canada", "india", "australia", "brazil", "mexico",
                "singapore", "japan", "china", "philippines", "argentina", "colombia", "new zealand",
                "south africa", "nigeria", "kenya", "egypt", "israel", "uae", "dubai", "pakistan", "americas", "latam", "apac",
                # US/other places whose names contain a European city
                "new york", "nyc", "new jersey", "new england", "new hampshire", "new south wales", "new brunswick",
                "new orleans", "new mexico", "new london", "east london, south africa", "london, ontario",
                "toronto", "vancouver", "san francisco", "bay area", "seattle", "chicago", "boston", "austin"]

REMOTE_WORDS = ["remote", "anywhere", "work from home", "wfh", "homeoffice", "home office", "home-based", "home based", "telecommute", "distributed", "fully remote"]


def fold(text: str) -> str:
    """lowercase + strip accents: 'Köln, Österreich' -> 'koln, osterreich'"""
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _has_word(text: str, word: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text) is not None


def _segments(text: str) -> list[str]:
    """Split multi-location strings: 'London, UK; New York, NY | Remote' -> pieces."""
    return [s.strip() for s in re.split(r"[;|/\n•]|\bor\b|\band\b", text) if s.strip()]


def is_remote_text(text: str) -> bool:
    t = fold(text)
    return any(_has_word(t, w) for w in REMOTE_WORDS)


def locate(text: str, country_hint: str = "") -> tuple[str, str]:
    """Return (country_code, city). country_code is '' if not Europe/unknown, 'EU' for Europe-wide.

    country_hint: an ISO code or country name the source already gave us.
    """
    hint = (country_hint or "").strip()
    if hint:
        code = _code_from_hint(hint)
        if code:
            city = _first_city(fold(text), code)
            return (code if code in EUROPE else "", city)

    t = fold(text)
    if not t.strip():
        return ("", "")

    for seg in _segments(t) or [t]:
        code, city = _locate_segment(seg)
        if code:
            return code, city
    return ("", "")


def _locate_segment(seg: str) -> tuple[str, str]:
    parts = [p.strip(" .()-") for p in seg.split(",")]
    tail = parts[-1] if len(parts) > 1 else ""
    if tail in NON_EU_SUFFIX:
        return ("", "")

    for name in sorted(COUNTRY_NAMES, key=len, reverse=True):
        if _has_word(seg, name):
            code = COUNTRY_NAMES[name]
            if name == "island" and "iceland" not in seg and "reykjavik" not in seg:
                continue  # "Long Island" etc.
            return code, _first_city(seg, code)

    for city in sorted(CITIES, key=len, reverse=True):
        if _has_word(seg, city):
            if any(_has_word(seg, w) for w in NON_EU_WORDS):
                return ("", "")
            return CITIES[city], city.title()

    if any(_has_word(seg, w) for w in REGION_WORDS) and not any(_has_word(seg, w) for w in NON_EU_WORDS):
        return ("EU", "")
    return ("", "")


def _first_city(text: str, code: str) -> str:
    for city in sorted(CITIES, key=len, reverse=True):
        if CITIES[city] == code and _has_word(text, city):
            return city.title()
    return ""


_ISO3 = {"GBR": "GB", "IRL": "IE", "DEU": "DE", "FRA": "FR", "NLD": "NL", "BEL": "BE", "ESP": "ES", "PRT": "PT",
         "ITA": "IT", "AUT": "AT", "CHE": "CH", "SWE": "SE", "NOR": "NO", "DNK": "DK", "FIN": "FI", "POL": "PL",
         "CZE": "CZ", "HUN": "HU", "ROU": "RO", "BGR": "BG", "GRC": "GR", "HRV": "HR", "SVN": "SI", "SVK": "SK",
         "EST": "EE", "LVA": "LV", "LTU": "LT", "LUX": "LU", "CYP": "CY", "MLT": "MT", "USA": "US", "CAN": "CA"}


def _code_from_hint(hint: str) -> str:
    h = hint.strip()
    if len(h) == 2 and h.isalpha():
        c = h.upper()
        return "GB" if c == "UK" else c
    if len(h) == 3 and h.upper() in _ISO3:
        return _ISO3[h.upper()]
    f = fold(h)
    if f in COUNTRY_NAMES:
        return COUNTRY_NAMES[f]
    if f in ("united states", "united states of america", "usa", "us"):
        return "US"
    return ""


def looks_non_european(text: str) -> bool:
    """True if the text clearly points outside Europe ('Austin, TX', 'Bangalore, India', 'Remote - US')."""
    t = fold(text)
    if any(_has_word(t, w) for w in NON_EU_WORDS + ["us", "remote us", "us remote", "new york", "san francisco",
                                                      "toronto", "bangalore", "bengaluru", "sydney", "melbourne"]):
        return True
    for seg in _segments(t):
        parts = [p.strip(" .()-") for p in seg.split(",")]
        if len(parts) > 1 and parts[-1] in NON_EU_SUFFIX:
            return True
    return False


def in_scope(country: str, allowed: set[str]) -> bool:
    """allowed may contain ISO codes plus 'EU' (Europe-wide remote)."""
    return bool(country) and country in allowed

# ---------------------------------------------------------------- text helpers (from JobRadar models.py)
_COMPANY_SUFFIX = re.compile(r"\b(ltd|limited|plc|llp|inc|gmbh|ag|sa|sas|bv|b\.v\.|nv|srl|spa|ab|as|oy|aps|uk|group|holdings)\b\.?", re.I)
_TITLE_NOISE = re.compile(r"\(.*?\)|\[.*?\]|\b(m/w/d|w/m/d|f/m/d|m/f/d|h/f|f/h|all genders?)\b|[-–|,].*?(remote|hybrid|london|uk)\s*$", re.I)


def norm_company(name: str) -> str:
    s = _COMPANY_SUFFIX.sub(" ", (name or "").lower())
    return re.sub(r"[^a-z0-9]+", "", s)


def norm_title(title: str) -> str:
    s = _TITLE_NOISE.sub(" ", (title or "").lower())
    s = s.replace("snr", "senior").replace("sr.", "senior").replace("sr ", "senior ").replace("jnr", "junior").replace("jr ", "junior ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_TAGS = re.compile(r"<[^>]+>")


def html_to_text(html: str, limit: int = 4000) -> str:
    if not html:
        return ""
    text = _html.unescape(html)          # Greenhouse double-escapes its HTML
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", text)
    text = _TAGS.sub(" ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:limit]

# ---------------------------------------------------------------- agencies (from JobRadar dedupe.py)
AGENCY_WORDS = re.compile(
    r"\b(recruit\w*|staffing|resourcing|personnel|headhunt\w*|executive search|talent (solutions|partners|acquisition partners)"
    r"|employment agency|job(s)? agency|placements?|interim)\b", re.I)

KNOWN_AGENCIES = {
    "hays", "michael page", "page personnel", "page executive", "robert half", "robert walters", "harvey nash",
    "adecco", "randstad", "manpower", "manpowergroup", "hudson", "huxley", "morgan mckinley", "spencer ogden",
    "pertemps", "search consultancy", "brook street", "office angels", "kelly services", "gi group", "venn group",
    "sanderson", "nigel frank", "jefferson frank", "harnham", "la fosse", "oliver bernard", "hydrogen group",
    "computer futures", "lorien", "experis", "matchtech", "gattaca", "investigo",
    "goodman masson", "marks sattin", "badenoch + clark", "badenoch and clark", "allegis", "aerotek", "teksystems",
    "austin fraser", "sthree", "real staffing", "annapurna", "jonathan lee", "spectrum it", "burns sheehan",
    "nicholson glover", "tenth revolution", "frank group", "cpl", "sigmar", "hays specialist",
    "reed specialist", "reed", "net talent", "oscar technology", "ashdown group", "career moves group",
    "client server", "akkodis", "modis", "people source consulting", "wallace hind", "eden scott",
    "nexus jobs", "allen associates", "senitor", "acceler8", "hamilton barnes", "trust in soda",
    "digital waffle", "searchability", "explore group", "intec select", "hunter selection",
    "service care solutions", "templine", "redline group", "hays plc",
}


def looks_like_agency(company: str) -> bool:
    c = (company or "").lower().strip()
    if not c:
        return False
    if AGENCY_WORDS.search(c):
        return True
    base = re.sub(r"\b(ltd|limited|plc|llp|uk|group|international|global|solutions)\b\.?", "", c).strip(" ,.-&")
    return base in KNOWN_AGENCIES



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
SITE_RANK = {"Company site": 0, "Indeed": 1, "LinkedIn": 2, "Glassdoor": 3, "Reed": 4, "Welcome to the Jungle": 5, "TargetJobs": 6,
             "hirebase": 7, "Adzuna": 8}
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


def _board(site, title, company, location, url, posted="", pattern=None, salary="", advert="", apply_url=""):
    """UK job boards searched for the UK: small towns default to GB. advert = the full ad when the source gives it."""
    country, city = locate(location)
    if not country and not looks_non_european(location):
        country = "GB"
    advert = str(advert or "")
    job = {"site": site, "ats": site.lower(), "title": str(title or "").strip(), "company": str(company or "").strip(),
           "location": str(location or "").strip(), "country": country, "city": city, "url": str(url or "").strip(),
           "applyUrl": str(apply_url or ""), "postedAt": str(posted or ""), "advert": advert,
           "hints": {"workplace": pattern or _pattern_from_ad(advert)}, "remote": pattern == "remote", "salaryText": salary}
    if not advert.strip():
        job["noAdvert"] = True
    return job


def _pattern_from_ad(advert):
    t = str(advert or "")[:6000].lower()
    if re.search(r"\bhybrid\b", t):
        return "hybrid"
    if re.search(r"\b(fully remote|remote[- ]first|100% remote|work from home)\b", t):
        return "remote"
    return None


def _pattern(*texts):
    t = " ".join(str(x or "") for x in texts).lower()
    return "remote" if ("remote" in t or "fulltime" == t.strip()) else ("hybrid" if ("hybrid" in t or "partial" in t) else None)


def from_indeed(it):
    lo, hi, unit = _g(it, "baseSalary.min"), _g(it, "baseSalary.max"), _g(it, "baseSalary.unitOfWork")
    sal = f"£{lo:,.0f} - £{hi:,.0f}/{str(unit).lower()}" if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) else ""
    return _board("Indeed", _g(it, "title"), _g(it, "employer.name"), _g(it, "location.city") or "United Kingdom",
                  _g(it, "jobUrl"), salary=sal, advert=_g(it, "description.text") or _g(it, "description"))


def from_reed(it):
    loc = _g(it, "location")
    pat = "remote" if _g(it, "is_remote") is True or str(_g(it, "location_type")).lower() == "remote" else _pattern(_g(it, "location_type"))
    return _board("Reed", _g(it, "title"), _g(it, "recruiter_name"), loc, _g(it, "job_url"), _g(it, "posted_date"), pat,
                  salary=_g(it, "salary_display"), advert=_g(it, "description_text"))


def from_glassdoor(it):
    loc = re.sub(r",\s*England$", "", str(_g(it, "location.name")))
    return _board("Glassdoor", _g(it, "title"), _g(it, "employer.name"), loc, _g(it, "url"), advert=_g(it, "description"))


def from_wttj(it):
    loc = ", ".join(x for x in [str(_g(it, "offices.city")), str(_g(it, "offices.country"))] if x)
    ad = "\n\n".join(str(x) for x in (_g(it, "summary"), _g(it, "description"), _g(it, "profile")) if x)
    return _board("Welcome to the Jungle", _g(it, "name"), _g(it, "organizationName"), loc, _g(it, "url"),
                  _g(it, "publishedAt"), _pattern(_g(it, "remote")), advert=ad, apply_url=_g(it, "applyUrl"))


def from_hirebase(it):
    return _board("hirebase", _g(it, "jobTitle"), _g(it, "companyName"), _g(it, "location"), _g(it, "applicationLink"),
                  _g(it, "datePosted"), _pattern(_g(it, "locationType")))


def from_adzuna_api(it):
    """Adzuna through Apify (solidcode/adzuna-scraper with fetchDescription): about 3 in 4 jobs come with the full ad."""
    ad = _g(it, "description")
    if len(str(ad or "")) <= len(str(_g(it, "descriptionSnippet") or "")) + 20:
        ad = ""                                   # only the search snippet: treated as a short ad (cloud reader)
    return _board("Adzuna", _g(it, "title"), _g(it, "company"), _g(it, "location"), _g(it, "jobUrl"), _g(it, "postedDate"),
                  salary=_g(it, "salary"), advert=ad)


def from_targetjobs(it):
    loc = _g(it, "location") or ", ".join(str(c) for c in (it.get("cities") or [])) or "United Kingdom"
    return _board("TargetJobs", _g(it, "title"), _g(it, "employer_name") or _g(it, "company_name"), loc, _g(it, "job_url"),
                  _g(it, "posted_at"), _pattern(_g(it, "workplace_type")), salary=_g(it, "salary_range.text"),
                  advert=_g(it, "description_full") or _g(it, "description"), apply_url=_g(it, "application_url"))


def from_adzuna_row(row):
    """A row from the PM sheet's All jobs tab: A date, B search, C title, D company, E location, F salary, G link."""
    r = list(row) + [""] * 10
    return _board("Adzuna", r[2], r[3], r[4], r[6], r[0], salary="" if r[5] == "Not stated" else r[5])


SOURCES = [("companies*", from_companies, "Company site"), ("linkedin*", from_linkedin, "LinkedIn"),
           ("indeed*", from_indeed, "Indeed"), ("reed*", from_reed, "Reed"), ("glassdoor*", from_glassdoor, "Glassdoor"),
           ("wttj*", from_wttj, "Welcome to the Jungle"), ("hirebase*", from_hirebase, "hirebase"),
           ("adzunaapi*", from_adzuna_api, "Adzuna"), ("targetjobs*", from_targetjobs, "TargetJobs")]


def load_raw(raw_dir, report):
    raw = []
    for pattern, fn, name in SOURCES:
        n = 0
        for p in sorted(glob.glob(os.path.join(raw_dir, pattern))):
            for it in load_items(p):
                if isinstance(it, dict):
                    raw.append(fn(it))
                    n += 1
        if n or name in ("Company site", "LinkedIn"):
            report["fetched"][name] = report["fetched"].get(name, 0) + n
    # the sheet's own Adzuna script is the backup: used only when the Apify Adzuna search brought nothing
    if not report["fetched"].get("Adzuna"):
        for p in sorted(glob.glob(os.path.join(raw_dir, "adzuna_[0-9]*"))):
            rows = read_sheet_rows(p)
            sel = [r for r in rows if len(r) > 9 and str(r[9]).strip().lower() == "adzuna" and not str(r[8]).strip()]
            raw += [from_adzuna_row(r) for r in sel]
            if sel:
                report["fetched"]["Adzuna (sheet backup)"] = report["fetched"].get("Adzuna (sheet backup)", 0) + len(sel)
    # ads read by the cloud reader (step after the first na-build) fill in jobs whose ad was too short
    texts = reader_texts(raw_dir)
    if texts:
        filled = 0
        for j in raw:
            t = texts.get(_url_key(j["url"]))
            if t and len(str(j.get("advert") or "").strip()) < AD_MIN_CHARS <= len(t):
                j["advert"] = t
                j.pop("noAdvert", None)
                filled += 1
        report["reader_filled"] = filled
    return raw


def _url_key(u):
    return re.sub(r"[?#].*$", "", str(u or "").strip().lower()).rstrip("/").replace("http://", "https://")


BLOCKED_PAGE = re.compile(r"confirm you are human|verify (that )?you are (a )?human|are you a robot|captcha|security check|"
                          r"unusual (activity|traffic)|access denied|sign in to (view|continue|see)|log in to (view|continue|see)", re.I)
# sites that put every automated reader behind a human check: their short ads go straight to Check manually
READER_SKIP = re.compile(r"(^|\.)adzuna\.", re.I)


def reader_texts(raw_dir):
    """url -> page text from the cloud reader's saved results (raw/reader_*.txt)."""
    out = {}
    for p in sorted(glob.glob(os.path.join(raw_dir, "reader*"))):
        for it in load_items(p):
            if not isinstance(it, dict):
                continue
            text = str(_g(it, "text") or "").strip()
            if BLOCKED_PAGE.search(text[:600]) or str(_g(it, "crawl.httpStatusCode") or "200")[:1] in "45":
                continue                          # a human check, sign-in wall or error page is not the ad: never get around it
            for u in (_g(it, "url"), _g(it, "crawl.loadedUrl"), _g(it, "metadata.canonicalUrl")):
                if u and text:
                    out.setdefault(_url_key(u), text)
    return out


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
        check_manually = False
        if len(str(text or "").strip()) < AD_MIN_CHARS:
            if not settings.get("after_reader"):
                report.setdefault("short", []).append({"url": j["url"], "title": j["title"], "company": j["company"], "site": j["site"]})
                continue                          # held: Collect has the cloud reader read these, then builds again
            check_manually = True                 # still unreadable after the cloud reader: the owner looks at it
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
        if check_manually:
            doc["checkManually"] = True
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
#   python na_engine.py na-ads   --out out --n 1      # print ArtifactData batch writes saving the full ads (collection "ads", doc id = Job ID)
#
# search.json / me.json / feed.json are saved Google Sheets get_values results
# ({"range": ..., "values": [[...], ...]}) for Search!A1:C40, Me!A1:C60 and Feed!A1:T5000.
# ======================================================================

SCHEMA = {
    "Search": {"collection": "search", "key": "setting", "columns": [
        ["Setting", "setting"], ["Value", "value"], ["What it does", "help"]]},
    "Me": {"collection": "me", "key": "fact", "columns": [
        ["Fact", "fact"], ["Value", "value"], ["Used for", "usedFor"]]},
    "Feed": {"collection": "feed", "key": "jobId", "columns": [
        ["Date found", "dateFound"], ["Source", "source"], ["Job title", "title"], ["Company", "company"],
        ["Location", "location"], ["Link", "link"], ["Facts", "facts"],
        ["Role searched", "role"], ["Decision", "decision"], ["Reason", "reason"], ["Requirements", "requirements"],
        ["CV", "cv"], ["CV score", "cvScore"], ["Status", "status"], ["Note", "note"],
        ["Date applied", "dateApplied"], ["Posted", "posted"], ["Job ID", "jobId"],
        ["Advert", "advert"], ["Apply link", "applyUrl"]]},
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
        elif "jobId" in d or "title" in d:      # a feed document -> its New jobs row (A..T)
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
RUN_CAP_USD = {"linkedin": 0.04, "indeed": 0.03, "glassdoor": 0.05, "wttj": 0.06, "reed": 0.05, "hirebase": 0.03,
               "targetjobs": 0.11, "reader": 0.10}   # most one search may spend
# actors charged by computing time instead of per job: a memory and time limit keep them small
CALL_OPTIONS = {"adzunaapi": {"memory": 512, "timeout": 300}, "reader": {"memory": 2048, "timeout": 300}}
MORNING_BEFORE_UK_HOUR = 10   # once-a-day searches (company career sites, TargetJobs) run only in the morning Collect run (08:47 UK)
TARGETS_MAX = 150                               # target companies checked per run
TARGETS_DAYS = 14                               # target companies: jobs posted in the last 2 weeks (only new ones are charged)
TARGETS_RESULTS = 30                            # at most 30 jobs from target companies per run (~$0.10)


def na_plan(search_rows, me_rows, settings=SETTINGS, user=False, uk_hour=None):
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
    if uk_hour is not None:
        p["uk_hour"] = uk_hour
    p["runs"] = source_runs(p, w, table(me_rows))
    return p


FIELDS = {
    "companies": "title,company_name,ats,workplace_type,remote,salary_min,salary_max,salary_currency,years_experience_min,visa_sponsorship,posted_at,job_url,apply_url,locations,country_codes,description_text",
    "linkedin": "id,url,title,location,postedDate,companyName,workType,salary,description,applyUrl",
    "indeed": "jobUrl,title,employer.name,location.city,baseSalary.min,baseSalary.max,baseSalary.unitOfWork,description.text",
    "reed": "title,recruiter_name,location,location_type,is_remote,job_url,posted_date,salary_display,description_text",
    "glassdoor": "title,employer.name,location.name,url,ageInDays,description",
    "wttj": "name,organizationName,offices.city,offices.country,remote,url,publishedAt,applyUrl,summary,description,profile",
    "adzunaapi": "title,company,location,salary,description,descriptionSnippet,jobUrl,postedDate",
    "targetjobs": "title,employer_name,company_name,location,cities,workplace_type,salary_range.text,description_full,job_url,application_url,posted_at",
    "reader": "url,crawl.loadedUrl,crawl.httpStatusCode,text",
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
        runs.append(run_spec(source, actor, inp, label, sum(1 for r in runs if r["source"] == source) + 1, max_charge))

    morning = p.get("uk_hour", uk_hour()) < MORNING_BEFORE_UK_HOUR
    if p.get("companies_input") and morning:      # company sites: the biggest Apify cost, and their jobs change slowly
        add("companies", "factpipe/ats-jobs-feed", p["companies_input"], "Company career sites", p.get("companies_budget_usd"))
    if p.get("targets_input") and morning:
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
        # one UK-wide search of today's jobs ($0.0005 a job, full ad included): wider or repeated searches re-buy the same jobs
        add("reed", "scrapersdelight/reed-jobs-scraper", {"keywords": roles[0], "datePosted": "today", "maxItems": 50, "fetchDetails": True,
                                                          "hideTrainingJobs": True, "hideSurveyJobs": True}, f"Reed {roles[0]}", 0.03)
    if uk and "glassdoor" in srcs:
        for r in roles[:2]:
            add("glassdoor", "valig/glassdoor-jobs-scraper", {"keywords": r, "location": "United Kingdom", "daysOld": 1, "limit": 60}, f"Glassdoor {r}")
    if uk and ("welcome to the jungle" in srcs or "wttj" in srcs):
        for r in roles[:2]:
            add("wttj", "clearpath/welcome-to-the-jungle-jobs-api", {"query": r, "searchOnlyInJobTitle": True, "countryCode": "GB", "datePosted": "1", "maxItems": 20, "includeDetails": True}, f"Welcome to the Jungle {r}")
    if uk and "adzuna" in srcs:
        add("adzunaapi", "solidcode/adzuna-scraper", {"searchQueries": list(roles[:2]), "country": "gb", "maxResults": 50, "maxDaysOld": "1",
                                                      "sortBy": "date", "fetchDescription": True}, "Adzuna")
    if uk and "targetjobs" in srcs and morning:
        add("targetjobs", "santamaria-automations/targetjobs-uk-scraper", {"searchQueries": list(roles[:3]), "sortBy": "newest", "includeJobDetails": True,
                                                                          "maxResults": 20, "maxResultsPerQuery": 10}, "TargetJobs (once a day)")
    if uk and "hirebase" in srcs:
        add("hirebase", "hirebase/remote-jobs", {"jobTitles": [r.title() if r.lower() != "apm" else "APM" for r in roles], "locations": ["United Kingdom"], "postedWithinDays": 3,
                                                  "maxResults": 150, "sortBy": "date_posted", "dedupeBy": "companyAndTitle"}, "hirebase")
    return runs


def run_spec(source, actor, inp, label, n=1, max_charge=None):
    r = {"source": source, "actor": actor, "input": inp, "fields": FIELDS[source],
         "raw_file": f"raw/{source}_{n}.txt", "label": label}
    max_charge = max_charge or RUN_CAP_USD.get(source)
    if max_charge:
        r["max_charge_usd"] = max_charge
    if source in CALL_OPTIONS:
        r["call_options"] = dict(CALL_OPTIONS[source])
    return r


def uk_hour(now=None):
    now = now or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo("Europe/London")).hour
    except Exception:
        return now.hour


def reader_run(short, n=1):
    """One cloud-reader run (apify/website-content-crawler) for the jobs whose ad was too short: it opens each page
    in Apify's cloud browser and returns its text. No Chrome."""
    urls, seen = [], set()
    for j in short:
        k = _url_key(j["url"])
        host = re.sub(r"^https?://", "", k).split("/")[0]
        if j["url"] and k not in seen and not READER_SKIP.search(host):
            seen.add(k)
            urls.append({"url": j["url"]})
    if not urls:
        return None
    return run_spec("reader", "apify/website-content-crawler",
                    {"startUrls": urls, "maxCrawlDepth": 0, "maxCrawlPages": len(urls), "crawlerType": "playwright:adaptive",
                     "saveMarkdown": False, "removeCookieWarnings": True}, f"Cloud reader for {len(urls)} short ads", n)


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
    rows, db, ads = [], [], []
    for did, (_, d) in sorted(candidates.items(), key=lambda kv: (kv[1][0], kv[1][1]["company"].lower())):
        if did in have_ids or d["url"].strip() in have_links:
            report["already_in_sheet"] += 1
            continue
        ad = ad_doc(did, d, found_at)
        if ad:
            ads.append(ad)
        cm = d.get("checkManually")
        values = [london_date, d["site"], d["title"], d["company"], d["location"], d["url"],
                  facts_text(d["facts"]), sorted(d["roles"], key=lambda r: (len(r), r.lower()))[0] if d["roles"] else "",
                  "Check manually" if cm else "", CHECK_MANUALLY_REASON if cm else "", "", "", "", "", "", "",
                  (d["postedAt"] or "")[:10], did,
                  sheet_safe(advert_excerpt(d["advert"])), sheet_safe(d.get("applyUrl", ""))]   # S Advert (start of it), T Apply link
        rows.append(values)
        _id, fields = row_to_doc("Feed", values, next_row)
        fields["factsData"] = d["facts"]
        db.append({"op": "set", "collection": collection, "doc_id": _id, "data": fields})
        next_row += 1
    report["added"] = len(rows)
    report["ads_saved"] = len(ads)
    report["check_manually"] = sum(1 for r in rows if r[8] == "Check manually")
    short = report.pop("short", [])
    report["short_ads"] = len(short)
    summary = (f"Fetched {', '.join(f'{k} {v}' for k, v in report['fetched'].items())}; added {len(rows)} new; "
               f"{report['already_in_sheet']} already in the sheet; {report['duplicates']} duplicates")
    top = sorted(report["dropped"].items(), key=lambda kv: -kv[1])[:4]
    if top:
        summary += "; dropped: " + ", ".join(f"{k} {v}" for k, v in top)
    if report.get("reader_filled") is not None:
        summary += f"; cloud reader filled {report['reader_filled']} short ads"
    if report["check_manually"]:
        summary += f"; {report['check_manually']} marked Check manually (ad unreadable)"
    os.makedirs(out_dir, exist_ok=True)
    json.dump(rows, open(os.path.join(out_dir, "rows.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(db, open(os.path.join(out_dir, "db.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(all_rows, open(os.path.join(out_dir, "all_rows.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(ads, open(os.path.join(out_dir, "ads.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(short, open(os.path.join(out_dir, "short.json"), "w", encoding="utf-8"), ensure_ascii=False)
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


CHECK_MANUALLY_REASON = "Ad couldn't be read, even by the cloud reader: open the link to judge it"
AD_MIN_CHARS = 200   # shorter than this is not a usable copy of the ad: Shortlist reads those on the web once
ADS_PER_BATCH = 40   # ArtifactData batch: at most 50 writes and 1 MiB; 40 full ads stay well under both


def ad_doc(job_id, d, saved_at, saved_by="Collect"):
    """The full advert as one document for Sift's "ads" collection (doc id = Job ID), so Shortlist and
    Tailor CVs read the saved copy instead of opening the ad on the web again. None when there is no usable text."""
    text = str(d.get("advert") or "")
    if "<" in text[:2000]:
        text = html_to_text(text, SETTINGS["advert_chars"])
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()[: SETTINGS["advert_chars"]]
    if d.get("noAdvert") or len(text) < AD_MIN_CHARS:
        return None
    return {"jobId": job_id, "title": d.get("title", ""), "company": d.get("company", ""), "link": d.get("url", ""),
            "applyUrl": d.get("applyUrl", ""), "source": d.get("site", ""), "text": text, "chars": len(text),
            "savedAt": saved_at, "savedBy": saved_by}


ADVERT_EXCERPT = 800   # characters of the advert kept in the sheet: enough to judge a job, small enough to append cheaply


def advert_excerpt(text):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(t) <= ADVERT_EXCERPT:
        return t
    cut = t[:ADVERT_EXCERPT].rsplit(" ", 1)[0]
    return cut + " …"


def sheet_safe(text):
    """A cell value Google Sheets keeps as plain text (no leading = + - @ that could read as a formula)."""
    t = str(text or "")
    return "'" + t if t[:1] in "=+-@" and t else t


def run_usage(path=None):
    """This task run's own Claude usage, added up from its session transcript (the newest .jsonl under
    ~/.claude/projects). tokens_in counts everything read (fresh, cache writes and cache reads); cached is the
    part read from cache, which costs far less. tool_calls counts tool uses."""
    if not path:
        files = glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True)
        files = [f for f in files if "/subagents/" not in f]
        if not files:
            return {"error": "no transcript found"}
        path = max(files, key=os.path.getmtime)
    u = {"tokens_in": 0, "cached": 0, "tokens_out": 0, "tool_calls": 0, "steps": 0}
    seen = set()
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get("message") if isinstance(d, dict) else None
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        mid = m.get("id") or d.get("uuid")
        us = m.get("usage") or {}
        if us and mid not in seen:            # one API reply can be split over several lines: count its usage once
            seen.add(mid)
            u["steps"] += 1
            u["tokens_in"] += sum(int(us.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            u["cached"] += int(us.get("cache_read_input_tokens") or 0)
            u["tokens_out"] += int(us.get("output_tokens") or 0)
        content = m.get("content")
        if isinstance(content, list):
            u["tool_calls"] += sum(1 for c in content if isinstance(c, dict) and c.get("type") == "tool_use")
    return u


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
    b.add_argument("--after-reader", action="store_true", help="second pass, after the cloud reader: ads still too short become Check manually rows")
    r = sub.add_parser("na-reader")
    r.add_argument("--out", default="out")
    r.add_argument("--save", default="reader.json")
    for name, size in (("na-rows", 40), ("na-db", 50), ("na-all", 100), ("na-ads", ADS_PER_BATCH)):
        c = sub.add_parser(name)
        c.add_argument("--out", default="out")
        c.add_argument("--n", type=int, required=True)
    sub.add_parser("na-usage")
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
        st = dict(SETTINGS, after_reader=a.after_reader)
        report, rows, db = na_build(read_values(a.search), read_values(a.me), read_values(a.feed), a.raw, a.out, settings=st, collection=a.collection)
        print(json.load(open(os.path.join(a.out, "run_row.json")))[2])
        print(f"{len(rows)} rows -> {(len(rows) + 39) // 40} append chunk(s) (na-rows); {(len(db) + 49) // 50} database batch(es) (na-db); "
              f"{report['all_jobs_rows']} collected jobs -> {(report['all_jobs_rows'] + 99) // 100} All jobs chunk(s) (na-all); "
              f"{report['ads_saved']} full ads -> {(report['ads_saved'] + ADS_PER_BATCH - 1) // ADS_PER_BATCH} ads batch(es) (na-ads); "
              + (f"{report['short_ads']} short ads held for the cloud reader (na-reader, then na-build --after-reader)" if report["short_ads"]
                 else f"{report['check_manually']} Check manually" if a.after_reader else "0 short ads: no reader needed"))
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
    elif a.cmd == "na-reader":
        spec = reader_run(json.load(open(os.path.join(a.out, "short.json"), encoding="utf-8")))
        json.dump(spec, open(a.save, "w", encoding="utf-8"), indent=1)
        print(f"{spec['label']}: saved to {a.save}" if spec else "no short ads: nothing to read")
    elif a.cmd == "na-ads":
        # one ArtifactData batch per chunk: each ad is written from its own file, so no ad text passes through the chat
        ads = json.load(open(os.path.join(a.out, "ads.json"), encoding="utf-8"))
        folder = os.path.abspath(os.path.join(a.out, "ads"))
        os.makedirs(folder, exist_ok=True)
        writes = []
        for ad in _chunk(ads, a.n, ADS_PER_BATCH):
            path = os.path.join(folder, ad["jobId"] + ".json")
            json.dump(ad, open(path, "w", encoding="utf-8"), ensure_ascii=False)
            writes.append({"op": "set", "collection": "ads", "doc_id": ad["jobId"], "file_path": path})
        print(json.dumps(writes))
    elif a.cmd == "na-usage":
        print(json.dumps(run_usage()))
    elif a.cmd == "na-schema":
        json.dump(SCHEMA, open(a.out, "w", encoding="utf-8"), indent=1)
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("na-"):
        sys.exit(na_main(sys.argv[1:]))
    sys.exit(main())
