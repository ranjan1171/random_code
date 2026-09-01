"""
matcher/profile.py — Ranjan Kumar's profile as structured matching data.
Converts the raw profile from config into TF-IDF-ready vectors and rule sets.
"""

import re
from typing import List, Set
from config import PROFILE, MATCHING


def normalize(text: str) -> str:
    """Lowercase, strip punctuation for keyword matching."""
    return re.sub(r"[^a-z0-9\s+#.]", " ", text.lower()).strip()


def tokenize(text: str) -> List[str]:
    """Split text into tokens, keeping compound terms like 'node.js', 'c++'."""
    tokens = normalize(text).split()
    return [t for t in tokens if len(t) > 1]


# ────────────────────────────────────────────
# Pre-computed profile sets for fast matching
# ────────────────────────────────────────────

# All skills normalized
SKILL_SET: Set[str] = {normalize(s) for s in PROFILE["skills"]}

# Primary skills (high-value matches)
PRIMARY_SKILL_SET: Set[str] = {normalize(s) for s in PROFILE["primary_skills"]}

# Target job title keywords
TARGET_TITLE_TOKENS: Set[str] = set()
for title in PROFILE["target_titles"]:
    TARGET_TITLE_TOKENS.update(tokenize(title))

# Acceptable locations (normalized)
ACCEPTABLE_LOCATIONS: Set[str] = {
    normalize(loc) for loc in PROFILE["acceptable_locations"]
}

# Target companies (normalized)
TARGET_COMPANIES: Set[str] = {
    normalize(c) for c in PROFILE["target_companies"]
}

# Dealbreaker phrases (normalized)
DEALBREAKER_PHRASES: List[str] = [
    normalize(d) for d in PROFILE["dealbreakers"]
]

# Combined profile text for TF-IDF document
PROFILE_TEXT = " ".join(PROFILE["skills"]) + " " + \
               " ".join(PROFILE["target_titles"]) + " " + \
               PROFILE.get("default_cover_letter", "")


TITLE_DEALBREAKERS = [
    "coordinator", "recruiter", "talent acquisition", "legal", "counsel", "sales",
    "account executive", "marketing", "human resources", "hr specialist", "office manager",
    "administrative", "payroll", "accountant", "receptionist", "event planner",
    "customer success", "support", "analyst", "investment", "av production",
    "quality inspector", "designer", "product manager", "program manager",
    "content", "copywriter", "social media", "community", "video",
]

# Strict whitelist: title MUST contain one of these to be considered a software dev job
SOFTWARE_DEV_KEYWORDS = [
    "software", "developer", "engineer", "sde", "swe", "programmer",
    "backend", "frontend", "fullstack", "full stack", "full-stack",
    "devops", "devsecops", "site reliability", "sre",
]


def _is_ascii_title(title: str) -> bool:
    """Return False if title contains non-ASCII characters (Japanese, Chinese, etc.)."""
    try:
        title.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def check_dealbreaker(job_title: str, job_text: str) -> tuple[bool, str]:
    """
    Returns (is_dealbreaker, reason) if the job is NOT a software developer role.
    
    Rules (in order):
      1. Reject non-ASCII titles (Japanese/Chinese/Korean postings)
      2. Reject titles matching explicit non-engineering keywords
      3. REQUIRE title to contain a software dev keyword (strict whitelist)
    """
    # 0. Reject non-ASCII titles immediately
    if not _is_ascii_title(job_title):
        return True, "Non-ASCII title (foreign language posting)"

    t_norm = normalize(job_title)

    # 1. Check title for non-engineering roles (Sales, HR, Support, etc.)
    for word in TITLE_DEALBREAKERS:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, t_norm):
            return True, f"Non-engineering role title: '{word}'"

    # 2. STRICT: title MUST contain a software dev keyword
    if not any(kw in t_norm for kw in SOFTWARE_DEV_KEYWORDS):
        return True, f"Title '{job_title}' does not contain software developer keywords"

    return False, ""


def location_score(job_location: str) -> float:
    """
    Returns 0.0–1.0 based on location acceptability.
    1.0 = perfect (Pune, Remote), 0.5 = acceptable (other India cities), 0.0 = not acceptable.
    """
    if not job_location:
        return 0.5  # unknown location — give benefit of doubt
    loc_lower = normalize(job_location)

    # Remote / WFH always OK
    if any(kw in loc_lower for kw in ["remote", "work from home", "wfh"]):
        return 1.0

    # Preferred cities
    preferred = ["pune", "bangalore", "bengaluru", "hyderabad", "mumbai"]
    if any(city in loc_lower for city in preferred):
        return 1.0

    # India in general
    if "india" in loc_lower or "pan india" in loc_lower:
        return 0.8

    # Hybrid anywhere in India
    if "hybrid" in loc_lower:
        return 0.8

    return 0.0


def company_bonus(company_name: str) -> float:
    """
    Returns 0.0–1.0 bonus if company is a target company.
    """
    if not company_name:
        return 0.0
    name_lower = normalize(company_name)
    for target in TARGET_COMPANIES:
        if target in name_lower or name_lower in target:
            return 1.0
    return 0.0


def experience_fit(job_text: str) -> float:
    """
    Checks if the job's experience requirement fits Ranjan's profile (1.5 years).
    Returns 0.0–1.0.
    """
    text = normalize(job_text)

    # Patterns like "0-2 years", "1+ years", "fresher", "entry level"
    fresher_patterns = [
        r"\b0[\s\-]?[to–-][\s]?[123]\s*years?\b",
        r"\bfresher\b", r"\bfresh\s+graduate\b",
        r"\bentry[\s\-]?level\b",
        r"\bjunior\b",
        r"\b[01]\+?\s*years?\s+(?:of\s+)?experience\b",
        r"\bsde[\s\-]?[12]?\b",
        r"\b[01][\s\-][23]\s*years?\b",
    ]

    senior_patterns = [
        r"\b[5-9]\+?\s*years?\b",
        r"\b1[0-9]\+?\s*years?\b",
        r"\bsenior\s+(?:staff|principal|architect)\b",
        r"\blead\s+engineer\b",
        r"\bengineering\s+manager\b",
    ]

    for pat in senior_patterns:
        if re.search(pat, text):
            return 0.3  # probably too senior

    for pat in fresher_patterns:
        if re.search(pat, text):
            return 1.0

    return 0.7  # no explicit requirement — neutral
