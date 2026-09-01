"""
qa_engine.py — Dynamic Q&A Fuzzy Matcher for ranjan.txt
Reads ranjan.txt, performs >=60% similarity fuzzy matching,
and auto-appends newly encountered questions to ranjan.txt.
"""

import os
import re
import logging
from typing import Optional, Tuple, List, Dict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

RANJAN_TXT_PATH = os.path.join(os.path.dirname(__file__), "ranjan.txt")


class QAEngine:
    AMBIGUOUS_PATTERNS = [
        "prefer", "preference", "choice", "which of the following",
        "willing to relocate", "willing to work", "work from the office",
        "office location", "work model", "relocate", "remote", "hybrid", "onsite", "on-site"
    ]

    # Canonical exact answer store: final known values for recurring Greenhouse fields.
    # This is the "final answer" layer; runtime fill should prefer these before fuzzy guess.
    CANONICAL_ANSWERS = {
        "where are you currently located": "Pune, Maharashtra, India",
        "location city": "Pune, Maharashtra, India",
        "country of residence": "India",
        "country": "India",
        "how did you hear about this job": "LinkedIn",
        "how did you hear about this opportunity at grafana": "LinkedIn",
        "what is your preferred office location": "Remote",
        "what is your current job title": "Software Developer 1",
        "what is your current company": "WhiteKlay",
        "what is your highest level of education": "Bachelor's degree",
        "what university did you attend": "National Institute of Technology, Jamshedpur",
        "what is your major": "Electronics and Communications Engineering",
        "do you now or will you in the future require immigration sponsorship to work at this company": "No",
        "do you now or will you in the future require immigration sponsorship to work at this employer": "No",
        "will you require sponsorship for employment visa status now or in the future": "No",
        "are you legally authorized to work in the country where this position is located": "Yes",
        "have you previously been employed by this company in any capacity": "No",
        "are you at least 18 years of age": "Yes",
        # Work authorization — MUST answer Yes for eligibility
        "are you currently eligible to work in your country of residence": "Yes",
        "are you eligible to work in your country of residence": "Yes",
        "are you authorized to work in the country in which this position is based": "Yes",
        "are you legally authorized to work in the country in which you are applying": "Yes",
        "do you now or will you in the future need sponsorship for employment visa status": "No",
        "do you now or will you in the future require immigration sponsorship": "No",
        "will you require visa sponsorship either now or in the near future": "No",
        # Demographics — precise answers
        "are you a person of transgender experience": "No",
        "what gender identity do you most closely identify with": "Male",
        "do you identify as hispanic or latino": "No",
        "are you hispanic or latino": "No",
        "veteran status": "I am not a protected veteran",
        "disability status": "No, I do not have a disability",
        # Consent and misc
        "do you consent to background check": "Yes",
        "are you willing to relocate": "Yes",
        "are you willing to work on-site": "Yes",
        # GitHub/GitLab username
        "what is your github username": "ranjan1171",
        "what is your gitlab username": "ranjan1171",
        # Accessibility
        "please let us know if there are any adjustments we can make": "No adjustments needed. Thank you.",
        "are there any adjustments we can make to assist you during the hiring": "No adjustments needed. Thank you.",
        # Company-specific questions
        "are you located in the uk spain sweden ireland or germany": "No",
        "are you located in spain uk sweden germany or ireland": "No",
        "are you based in austin us or london uk": "No",
        # Coinbase-specific questions
        "to your knowledge, were you referred to this position by a senior leader or decision-maker at a current or prospective institutional client, business partner, or vendor of coinbase": "No",
        "to your knowledge were you referred to this position by a senior leader or decisionmaker at a current or prospective institutional client business partner or vendor of coinbase": "No",
    }

    def __init__(self, filepath: str = None):
        self.filepath = filepath or RANJAN_TXT_PATH
        self.qa_pairs: List[Dict[str, str]] = []
        self.load_questions()

    @staticmethod
    def normalize_question(raw_question: str) -> str:
        if not raw_question:
            return ""
        q = raw_question.lower()
        q = re.sub(r'[^a-z0-9\s]', ' ', q)
        q = re.sub(r'\s+', ' ', q).strip()
        return q

    def get_exact_answer(self, raw_question: str) -> Optional[str]:
        """Return a canonical final answer if the question matches a known pattern exactly."""
        if not raw_question or not raw_question.strip():
            return None

        q_norm = self.normalize_question(raw_question)
        if not q_norm:
            return None

        # Exact stored Q/A match first
        for item in self.qa_pairs:
            if self.normalize_question(item["question"]) == q_norm:
                return item["answer"]

        # Canonical pattern aliases next
        for key, answer in self.CANONICAL_ANSWERS.items():
            if q_norm == key or q_norm in key or key in q_norm:
                return answer

        return None

    @classmethod
    def is_ambiguous_question(cls, raw_question: str) -> bool:
        q = (raw_question or "").lower()
        return any(p in q for p in cls.AMBIGUOUS_PATTERNS)

    def load_questions(self):
        """Parse ranjan.txt into Q&A dictionary list with flexible format handling."""
        self.qa_pairs = []
        if not os.path.exists(self.filepath):
            logger.warning(f"[QAEngine] File not found: {self.filepath}")
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # 1. Parse standard Q: and A: blocks
            blocks = content.split("Q:")
            for b in blocks:
                if not b.strip():
                    continue
                parts = b.split("A:")
                if len(parts) >= 2:
                    q = parts[0].strip().replace("\n", " ")
                    raw_a = parts[1].split("\n\n")[0].strip().replace("\n", " ")
                    # Clean markdown links/emails
                    a = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', raw_a).strip()
                    if q and a:
                        self.qa_pairs.append({"question": q, "answer": a})

            # 2. Parse freeform Question / Answer lines (lines with ? or ending in colon)
            lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#") and not l.startswith("=")]
            for i in range(len(lines) - 1):
                curr = lines[i]
                nxt = lines[i+1]
                if (curr.endswith("?") or curr.endswith(":")) and not curr.startswith("Q:") and not curr.startswith("A:"):
                    clean_q = re.sub(r'^[QA]:\s*', '', curr).strip()
                    clean_a = re.sub(r'^[QA]:\s*', '', nxt).strip()
                    clean_a = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean_a).strip()
                    if clean_q and clean_a and not clean_q.startswith("A:"):
                        self.qa_pairs.append({"question": clean_q, "answer": clean_a})

            logger.info(f"[QAEngine] Loaded {len(self.qa_pairs)} Q&A pair(s) from ranjan.txt")
        except Exception as e:
            logger.error(f"[QAEngine] Error loading ranjan.txt: {e}")

    def find_answer(self, raw_question: str, min_similarity: float = 0.60) -> Tuple[Optional[str], float, Optional[str]]:
        """
        Exact-match lookup first, then fuzzy match against ranjan.txt Q&A pairs.
        Returns: (answer, similarity_score, matched_question)
        """
        if not raw_question or not raw_question.strip():
            return None, 0.0, None

        exact_answer = self.get_exact_answer(raw_question)
        if exact_answer is not None:
            if self.is_ambiguous_question(raw_question):
                logger.info(f"[QAEngine] Exact match exists but question is ambiguous and blocked: '{raw_question[:80]}'")
                return None, 1.0, raw_question
            logger.info(f"[QAEngine] Exact canonical match for '{raw_question[:60]}': '{exact_answer}'")
            return exact_answer, 1.0, raw_question

        q_clean = re.sub(r'[^a-zA-Z0-9\s]', '', raw_question.lower()).strip()
        best_answer = None
        best_score = 0.0
        best_matched_q = None

        for item in self.qa_pairs:
            stored_q = item["question"]
            s_clean = re.sub(r'[^a-zA-Z0-9\s]', '', stored_q.lower()).strip()

            STOP_WORDS = {
                "a", "an", "the", "and", "or", "to", "of", "for", "with", "on", "in", "is", "are",
                "do", "did", "you", "your", "have", "has", "at", "before", "will", "would", "please"
            }

            q_clean_filtered = " ".join([w for w in q_clean.split() if w not in STOP_WORDS])
            s_clean_filtered = " ".join([w for w in s_clean.split() if w not in STOP_WORDS])
            ratio = SequenceMatcher(None, q_clean_filtered, s_clean_filtered).ratio()

            q_words = {w for w in q_clean.split() if w not in STOP_WORDS}
            s_words = {w for w in s_clean.split() if w not in STOP_WORDS}

            if q_words:
                overlap = len(q_words & s_words) / len(q_words)
            else:
                overlap = len(set(q_clean.split()) & set(s_clean.split())) / max(len(q_clean.split()), 1)

            combined_score = max(ratio, (ratio * 0.7 + overlap * 0.3))

            if combined_score >= best_score:
                best_score = combined_score
                best_answer = item["answer"]
                best_matched_q = stored_q

        if best_answer is not None and str(best_answer).strip().lower() in {"need user input", "need job-specific answer", "need user input."}:
            logger.info(f"[QAEngine] Ambiguous/blocked answer for '{raw_question[:50]}': '{best_answer}'")
            return None, best_score, best_matched_q

        if best_score >= min_similarity:
            if self.is_ambiguous_question(raw_question):
                logger.info(f"[QAEngine] Question is ambiguous and blocked: '{raw_question[:80]}' (score={best_score*100:.1f}%)")
                return None, best_score, best_matched_q

            logger.info(f"[QAEngine] Matched '{raw_question[:50]}' -> '{best_matched_q[:50]}' ({best_score*100:.1f}%) => Answer: '{best_answer}'")
            return best_answer, best_score, best_matched_q

        logger.info(f"[QAEngine] No match >= 60% for '{raw_question[:50]}' (Best was {best_score*100:.1f}%)")
        return None, best_score, None

    def record_question(self, question: str, answer: str):
        """Append a newly encountered question & answer to ranjan.txt cleanly."""
        if not question or not question.strip():
            return

        # Skip recording stupid or foreign fallback values
        if any(bad in answer.lower() for bad in ["nunca", "espero", "british indian ocean", "cannot recall"]):
            return

        # Check if already exists in qa_pairs
        q_clean = question.strip()
        for item in self.qa_pairs:
            if item["question"].strip().lower() == q_clean.lower():
                return  # Already recorded

        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(f"\n\nQ: {q_clean}\nA: {answer.strip()}\n")
            self.qa_pairs.append({"question": q_clean, "answer": answer.strip()})
            logger.info(f"[QAEngine] Recorded new Q&A pair to ranjan.txt: Q: '{q_clean}' -> A: '{answer.strip()}'")
        except Exception as e:
            logger.error(f"[QAEngine] Error appending to ranjan.txt: {e}")


# Singleton instance
_qa_engine = None


def get_qa_engine() -> QAEngine:
    global _qa_engine
    if _qa_engine is None:
        _qa_engine = QAEngine()
    return _qa_engine
