import re
from bs4 import BeautifulSoup

with open('c:/Users/HP/OneDrive/Desktop/auto_job_apply/auto_apply_system/logs/greenhouse_error_1788071858.html', 'r', encoding='utf-8', errors='ignore') as f:
    html = f.read()

# Find the exact HTML around question_68205787
for match in re.finditer(r'.{0,300}question_68205787.{0,500}', html):
    print(match.group(0)[:800])
    print("---")
