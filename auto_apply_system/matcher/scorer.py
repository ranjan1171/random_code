"""
matcher/scorer.py — Job-to-Profile scoring engine.
Uses TF-IDF cosine similarity + rule-based scoring to produce a 0–100 match score.
"""

import re
import math
import logging
from typing import Dict, Any, Tuple
from collections import Counter

from config import MATCHING
from matcher.profile import (
    SKILL_SET, PRIMARY_SKILL_SET, TARGET_TITLE_TOKENS,
    PROFILE_TEXT, check_dealbreaker, location_score,
    company_bonus, experience_fit, normalize, tokenize
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────
# TF-IDF helpers (pure Python, no sklearn dep)
# ────────────────────────────────────────────

def _tf(tokens: list) -> Dict[str, float]:
    """Term frequency."""
    count = Counter(tokens)
    total = len(tokens) or 1
    return {t: c / total for t, c in count.items()}


def _idf_boost(term: str) -> float:
    """
    Simple IDF approximation — technical terms get higher weight.
    We use a hand-crafted boost for known important terms.
    """
    HIGH_VALUE = {
        "python", "kafka", "rust", "distributed", "backend", "system",
        "hft", "latency", "real-time", "pipeline", "microservice",
        "engineering", "api", "concurrent", "async", "scalable",
    }
    if term in HIGH_VALUE:
        return 2.0
    if term in PRIMARY_SKILL_SET:
        return 1.8
    if term in SKILL_SET:
        return 1.4
    return 1.0


def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    """Cosine similarity between two TF-IDF vectors."""
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dot = sum(vec_a[t] * vec_b[t] * _idf_boost(t) for t in common)
    mag_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# Pre-compute profile TF vector
_profile_tokens = tokenize(PROFILE_TEXT)
_PROFILE_TF = _tf(_profile_tokens)


# ─────────────────────────────────────────────
# Main scorer
# ─────────────────────────────────────────────

def score_job(job: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    Score a job against Ranjan's profile.

    Returns:
        (score: float 0-100, details: dict with breakdown)
    """
    title = job.get("title", "")
    company = job.get("company", "")
    location = job.get("location", "")
    description = job.get("description", "")

    # Combine all job text for matching
    full_text = f"{title} {company} {description}"

    # ── 1. DEALBREAKER CHECK ──────────────────
    is_db, db_reason = check_dealbreaker(title, full_text)
    if is_db:
        logger.debug(f"Dealbreaker: {title} @ {company} — {db_reason}")
        return 0.0, {
            "is_dealbreaker": True,
            "dealbreaker_reason": db_reason,
            "skill_score": 0,
            "title_score": 0,
            "location_score": 0,
            "company_score": 0,
            "experience_score": 0,
            "final_score": 0,
        }

    weights = MATCHING["weights"]

    # ── 2. SKILL OVERLAP (TF-IDF cosine) ─────
    job_tokens = tokenize(full_text)
    job_tf = _tf(job_tokens)
    cosine = _cosine_similarity(_PROFILE_TF, job_tf)
    skill_score = min(cosine * 300, 100)  # scale to 0-100

    # Bonus for direct primary skill mentions
    primary_hits = sum(1 for sk in PRIMARY_SKILL_SET if sk in full_text.lower())
    primary_bonus = min(primary_hits * 5, MATCHING["primary_skill_bonus"])
    skill_score = min(skill_score + primary_bonus, 100)

    # Count exact skill matches for details
    matched_skills = [sk for sk in SKILL_SET if normalize(sk) in normalize(full_text)]

    # ── 3. TITLE MATCH ───────────────────────
    title_tokens = set(tokenize(title))
    title_overlap = len(title_tokens & TARGET_TITLE_TOKENS)
    title_score = min(title_overlap * 25, 100)  # 4 hits = 100

    # Boost for exact known titles
    title_lower = title.lower()
    exact_title_match = any(
        t.lower() in title_lower for t in [
            "software developer", "software engineer", "backend engineer",
            "backend developer", "sde", "systems engineer"
        ]
    )
    if exact_title_match:
        title_score = max(title_score, 80)

    # ── 4. LOCATION MATCH ────────────────────
    loc_score = location_score(location) * 100

    # ── 5. COMPANY BONUS ─────────────────────
    comp_score = company_bonus(company) * 100

    # ── 6. EXPERIENCE FIT ────────────────────
    exp_score = experience_fit(full_text) * 100

    # ── WEIGHTED FINAL SCORE ─────────────────
    final = (
        skill_score    * weights["skill_overlap"] +
        title_score    * weights["title_match"] +
        loc_score      * weights["location_match"] +
        comp_score     * weights["company_bonus"] +
        exp_score      * weights["experience_fit"]
    )
    final = round(min(final, 100), 1)

    details = {
        "is_dealbreaker": False,
        "skill_score": round(skill_score, 1),
        "title_score": round(title_score, 1),
        "location_score": round(loc_score, 1),
        "company_score": round(comp_score, 1),
        "experience_score": round(exp_score, 1),
        "primary_skill_hits": primary_hits,
        "matched_skills": matched_skills[:15],  # top 15
        "final_score": final,
    }

    logger.debug(
        f"Score {final:.1f} — {title} @ {company} "
        f"[skill={skill_score:.0f} title={title_score:.0f} "
        f"loc={loc_score:.0f} comp={comp_score:.0f}]"
    )
    return final, details


def is_good_match(score: float) -> bool:
    """True if score meets the minimum threshold."""
    return score >= MATCHING["min_score"]
