import re, glob
from bs4 import BeautifulSoup

files = sorted(glob.glob('c:/Users/HP/OneDrive/Desktop/auto_job_apply/auto_apply_system/logs/greenhouse_error_*.html'))
if not files:
    print("No error HTML files found.")
    exit(0)

latest_file = files[-1]
print(f"Analyzing latest error log: {latest_file}\n")

with open(latest_file, 'r', encoding='utf-8', errors='ignore') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

# Find all error messages
errors = soup.find_all(class_=re.compile(r'error|helper-text'))
print("=== ERROR ELEMENTS ===")
for e in errors:
    text = e.get_text(strip=True)
    if 'required' in text.lower():
        parent = e.find_parent('div')
        label = parent.find('label') if parent else None
        label_text = label.get_text(strip=True) if label else "UNKNOWN"
        print(f"  MISSING: '{label_text}' -> {text}")

# Also find inputs with aria-invalid=true  
invalid_inputs = soup.find_all(attrs={"aria-invalid": "true"})
print(f"\n=== INVALID INPUTS ({len(invalid_inputs)}) ===")
for inp in invalid_inputs:
    inp_id = inp.get('id', '')
    label = soup.find('label', attrs={"for": inp_id})
    label_text = label.get_text(strip=True) if label else "UNKNOWN"
    val = inp.get('value', '')
    print(f"  INVALID: id='{inp_id}' label='{label_text}' value='{val}'")
