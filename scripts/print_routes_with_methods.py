import sys
sys.path.insert(0, r'c:/Users/lenovo/Desktop/filernow backend')
from app.main import app
for route in app.routes:
    print(route.path, getattr(route, 'methods', None))
