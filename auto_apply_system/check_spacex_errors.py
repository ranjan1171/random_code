import glob, re
from bs4 import BeautifulSoup

files = sorted(glob.glob('c:/Users/HP/OneDrive/Desktop/auto_job_apply/auto_apply_system/logs/greenhouse_error_*.html'))
print(f"Total error HTML files: {len(files)}")
for file in files[-5:]:
    print(f"\n--- File: {file}")
    with open(file, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    title_el = soup.find('title')
    title = title_el.get_text(strip=True) if title_el else 'Unknown'
    print(f"  Job Title: {title}")
    
    invalid_inputs = soup.find_all(attrs={'aria-invalid': 'true'})
    print(f"  Invalid Inputs Count: {len(invalid_inputs)}")
    for inp in invalid_inputs:
        inp_id = inp.get('id', '')
        label = soup.find('label', attrs={'for': inp_id})
        label_text = label.get_text(strip=True) if label else 'UNKNOWN'
        val = inp.get('value', '')
        print(f"    INVALID: id='{inp_id}' label='{label_text}' val='{val}'")

    # Also check any elements with class error-message or required
    err_msgs = soup.find_all(class_=re.compile(r'error-message|field-error|asterisk'))
    for em in err_msgs:
        print(f"    ERROR MSG: {em.get_text(strip=True)}")
