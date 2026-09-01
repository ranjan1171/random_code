from qa_engine import get_qa_engine

qa = get_qa_engine()

checks = [
    ("Where are you currently located?", "Pune, Maharashtra, India"),
    ("Country of residence?", "India"),
    ("How did you hear about this job?", "LinkedIn"),
    ("Would you prefer to work remotely, hybrid, or on-site?", None),
]

for question, expected in checks:
    answer, score, matched = qa.find_answer(question)
    print(f"Q: {question}\nA: {answer!r}\nscore={score}\nmatched={matched!r}\n")
    if expected is not None:
        assert answer == expected, f"expected {expected!r}, got {answer!r}"
    else:
        assert answer is None, f"expected no guess, got {answer!r}"

print("VALIDATION_OK")
