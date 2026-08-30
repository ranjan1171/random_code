import re
import glob

files = sorted(glob.glob('c:/Users/HP/OneDrive/Desktop/auto_job_apply/auto_apply_system/logs/greenhouse_error_*.html'))
if files:
    with open(files[-1], 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    
    # Find react-select option IDs
    ids = re.findall(r'id="(react-select[^"]*option[^"]*)"', html)
    print(f'Found {len(ids)} react-select option IDs')
    for i in ids[:10]:
        print(f'  {i}')
    
    # Also check for select__option class
    classes = re.findall(r'class="([^"]*select__option[^"]*)"', html)
    print(f'\nFound {len(classes)} select__option classes')
    for c in classes[:5]:
        print(f'  {c}')
    
    # Check what the actual dropdown option elements look like
    # Find any div with "-option-" in its id
    option_divs = re.findall(r'<div[^>]*id="[^"]*-option-[^"]*"[^>]*>', html)
    print(f'\nFound {len(option_divs)} div elements with -option- in id')
    for d in option_divs[:5]:
        print(f'  {d}')
else:
    print('No error HTML files found')
