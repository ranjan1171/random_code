from qa_engine import get_qa_engine

qa = get_qa_engine()


def test_ambiguous_preference_requires_user_input():
    answer, score, matched = qa.find_answer("Would you prefer to work remotely, hybrid, or on-site?", min_similarity=0.60)
    assert answer is None, f"Expected no guess for ambiguous preference question, got {answer!r} (score={score}, match={matched!r})"


def test_exact_known_question_still_matches():
    answer, score, matched = qa.find_answer("How did you hear about this job?", min_similarity=0.60)
    assert answer == "LinkedIn", f"Expected exact match, got {answer!r} (score={score}, match={matched!r})"


def test_exact_canonical_match_for_location_and_country():
    loc_answer, loc_score, _ = qa.find_answer("Where are you currently located?", min_similarity=0.60)
    assert loc_answer == "Pune, Maharashtra, India", f"Expected exact canonical location, got {loc_answer!r}"

    country_answer, country_score, _ = qa.find_answer("Country of residence?", min_similarity=0.60)
    assert country_answer == "India", f"Expected exact canonical country answer, got {country_answer!r}"


print(f"Total loaded Q&A pairs from ranjan.txt: {len(qa.qa_pairs)}\n")
for pair in qa.qa_pairs[:15]:
    print(f"  Q: {pair['question'][:60]} -> A: {pair['answer'][:60]}")
