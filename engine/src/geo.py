"""Work out whether a job is in the UK / Europe from messy location text.

Job sites write locations every possible way: "London", "London, England, UK",
"Remote - EMEA", "Berlin, Deutschland", "Hybrid (Amsterdam)", "London, ON" (that one is Canada).
`locate()` turns any of those into (country_code, city, is_europe_wide).
"""
from __future__ import annotations

import re
import unicodedata

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
