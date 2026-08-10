import sys
sys.path.insert(0, r'c:/Users/lenovo/Desktop/filernow backend')
from app.main import app
spec = app.openapi()
for path in [
    '/api/notifications',
    '/api/notifications/unread-count',
    '/api/notifications/read',
    '/api/notifications/{notification_id}',
    '/api/notifications/ws/{user_id}',
]:
    print('PATH:', path)
    print(spec['paths'].get(path))
    print('---')
