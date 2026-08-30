from qa_engine import get_qa_engine

qa = get_qa_engine()
print(f"Total loaded Q&A pairs from ranjan.txt: {len(qa.qa_pairs)}\n")
for pair in qa.qa_pairs[:15]:
    print(f"  Q: {pair['question'][:60]} -> A: {pair['answer'][:60]}")
