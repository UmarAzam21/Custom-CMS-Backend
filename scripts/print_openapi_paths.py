import sys
sys.path.insert(0, r'c:/Users/lenovo/Desktop/filernow backend')
from app.main import app
spec = app.openapi()
for p in sorted(spec.get('paths', {}).keys()):
    print(p)
