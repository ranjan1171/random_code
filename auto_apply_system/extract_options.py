import re
from bs4 import BeautifulSoup

def find_options_in_scripts(filename, keyword):
    print(f'\n--- {keyword} ---')
    with open(f'c:/Users/HP/OneDrive/Desktop/auto_job_apply/auto_apply_system/logs/{filename}', 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.find_all('script'):
        if script.string:
            text = script.string
            if keyword.lower() in text.lower():
                matches = re.findall(r'"name":"([^"]+)"', text)
                if not matches:
                    matches = re.findall(r'"label":"([^"]+)"', text)
                
                if matches:
                    print('Possible options found:')
                    for m in matches:
                        print(f' - {m}')
                    return
                print('Found keyword but no obvious array. Snippet:', text[:200])

find_options_in_scripts('greenhouse_error_1788068624.html', 'legally authorized')
find_options_in_scripts('greenhouse_error_1788068662.html', 'cities are you available')
