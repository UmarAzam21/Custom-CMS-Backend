import sys
sys.path.insert(0, r'c:/Users/lenovo/Desktop/filernow backend')
from app.main import app
spec = app.openapi()
print('OPENAPI PATHS')
for path in sorted(spec.get('paths', {}).keys()):
    print(path)
print('---')
print('ROUTES')
for route in app.routes:
    print(route.path, getattr(route, 'methods', None))
