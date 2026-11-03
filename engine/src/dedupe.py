"""Recruitment-agency detection and duplicate collapsing.

In the UK the same role is often posted by the employer *and* several agencies.
We keep one "primary" listing per role and point the copies at it.
Preference: company's own careers board > job board (direct employer) > agency.
"""
from __future__ import annotations

import re

from .models import Job, norm_title

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


SOURCE_RANK = {"greenhouse": 0, "greenhouse_eu": 0, "lever": 0, "lever_eu": 0, "ashby": 0, "workable": 0,
               "smartrecruiters": 0, "recruitee": 0, "personio": 0, "workday": 0,
               "reed": 1, "adzuna": 2, "arbeitnow": 2}


def rank(job_row: dict) -> tuple:
    return (1 if job_row["is_agency"] else 0, SOURCE_RANK.get(job_row["source"], 3), job_row["first_seen"] or "")


def agency_key(title: str, city: str, country: str) -> str:
    """Agencies hide the employer, so group agency posts by role + place."""
    return f"{norm_title(title)}|{(city or country).lower()}"


def mark(job: Job) -> Job:
    job.is_agency = looks_like_agency(job.company)
    return job
