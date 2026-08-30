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
    def __init__(self, filepath: str = None):
        self.filepath = filepath or RANJAN_TXT_PATH
        self.qa_pairs: List[Dict[str, str]] = []
        self.load_questions()

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
        Fuzzy match raw_question against ranjan.txt Q&A pairs.
        Returns: (answer, similarity_score, matched_question)
        """
        if not raw_question or not raw_question.strip():
            return None, 0.0, None

        q_clean = re.sub(r'[^a-zA-Z0-9\s]', '', raw_question.lower()).strip()
        best_answer = None
        best_score = 0.0
        best_matched_q = None

        for item in self.qa_pairs:
            stored_q = item["question"]
            s_clean = re.sub(r'[^a-zA-Z0-9\s]', '', stored_q.lower()).strip()

            # Additional word overlap score (excluding common stop words to prevent false positives)
            STOP_WORDS = {
                "a", "an", "the", "and", "or", "to", "of", "for", "with", "on", "in", "is", "are", 
                "do", "did", "you", "your", "have", "has", "at", "before", "will", "would", "please"
            }
            
            # SequenceMatcher ratio on cleaned strings
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

        if best_score >= min_similarity:
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
            logger.error(f"[QAEngine] Error recording question to ranjan.txt: {e}")
            logger.info(f"[QAEngine] Saved new Q&A pair to ranjan.txt: Q: '{question[:40]}' => A: '{answer}'")
        except Exception as e:
            logger.error(f"[QAEngine] Error appending to ranjan.txt: {e}")


# Singleton instance
_qa_engine = None


def get_qa_engine() -> QAEngine:
    global _qa_engine
    if _qa_engine is None:
        _qa_engine = QAEngine()
    return _qa_engine
