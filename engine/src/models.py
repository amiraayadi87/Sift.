"""The one shape every source is converted into."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict


@dataclass
class Job:
    source: str            # e.g. "greenhouse", "adzuna"
    source_id: str         # the id the source gives the job
    title: str
    company: str
    url: str
    location: str = ""     # raw location text from the source
    country: str = ""      # ISO-2 code we worked out, e.g. "GB", "DE" ("EU" = Europe-wide remote)
    city: str = ""
    remote: bool = False
    posted_at: str = ""    # ISO date (YYYY-MM-DD) when known
    employment_type: str = ""
    department: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    description: str = ""  # plain text, trimmed
    is_agency: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        """Stable id for this exact listing."""
        return f"{self.source}:{self.source_id}"

    @property
    def fingerprint(self) -> str:
        """Same role posted in several places gets the same fingerprint."""
        key = "|".join([norm_company(self.company), norm_title(self.title), (self.city or self.country).lower()])
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    def to_row(self) -> dict:
        d = asdict(self)
        d.pop("extra")
        return d


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
    import html as _html
    if not html:
        return ""
    text = _html.unescape(html)          # Greenhouse double-escapes its HTML
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", text)
    text = _TAGS.sub(" ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:limit]
