"""Derive an application `source` label from a job_link URL."""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse


# Job boards and aggregators. Order matters — more specific patterns first.
# Matching is substring on the hostname, so `jobs.lever.co` matches `lever.co`.
DOMAIN_MAP: tuple[tuple[str, str], ...] = (
    # International
    ("linkedin.com", "LinkedIn"),
    ("indeed.com", "Indeed"),
    ("glassdoor.com", "Glassdoor"),
    ("greenhouse.io", "Greenhouse"),
    ("lever.co", "Lever"),
    ("myworkdayjobs.com", "Workday"),
    ("workday.com", "Workday"),
    ("wellfound.com", "Wellfound"),
    ("angel.co", "Wellfound"),
    ("otta.com", "Otta"),
    ("welcometothejungle.com", "Otta"),
    ("news.ycombinator.com", "Hacker News"),
    # Poland
    ("pracuj.pl", "Pracuj.pl"),
    ("justjoin.it", "JustJoin.it"),
    ("nofluffjobs.com", "NoFluffJobs"),
    ("bulldogjob.pl", "Bulldogjob"),
    ("theprotocol.it", "TheProtocol"),
    ("rocketjobs.pl", "Rocketjobs"),
)

# Path / query substrings that suggest a company's own careers page.
# Matched lowercase against path + query only, never the host.
COMPANY_SITE_SIGNALS: tuple[str, ...] = (
    "careers",
    "jobs",
    "job/",
    "job=",
    "apply",
    "positions",
    "openings",
    "hiring",
)

# Subdomain prefixes that strongly suggest a company's careers site.
COMPANY_SITE_SUBDOMAINS: tuple[str, ...] = (
    "jobs.",
    "careers.",
    "apply.",
    "hiring.",
)

MANUAL = "Manual"
COMPANY_SITE = "Company Site"
OTHER = "Other"


def derive_source(job_link: Optional[str]) -> str:
    """Return a short source label for the given job URL.

    Precedence:
      1. Missing / blank link           -> "Manual"
      2. Known job board domain         -> that board's label
      3. Path/query or subdomain looks  -> "Company Site"
         like a careers page
      4. Anything else                  -> "Other"
    """
    if not job_link or not job_link.strip():
        return MANUAL

    candidate = job_link.strip()
    # Add a scheme if missing so urlparse treats it as a URL, not a path.
    if "://" not in candidate:
        candidate = "https://" + candidate

    try:
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return OTHER

    if not host:
        return MANUAL

    for needle, label in DOMAIN_MAP:
        if needle in host:
            return label

    surface = (parsed.path + "?" + parsed.query).lower()
    if any(signal in surface for signal in COMPANY_SITE_SIGNALS):
        return COMPANY_SITE

    if host.startswith(COMPANY_SITE_SUBDOMAINS):
        return COMPANY_SITE

    return OTHER