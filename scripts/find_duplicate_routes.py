from pathlib import Path
p=Path('app/router.py')
text=p.read_text()
for i,line in enumerate(text.splitlines(),start=1):
    if '/api/public/contact' in line or '/api/public/pages/{slug}' in line:
        print(i, line)
