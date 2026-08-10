from app.main import app
print('\n'.join(sorted({r.path for r in app.routes})))
