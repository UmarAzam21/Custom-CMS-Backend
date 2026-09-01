from sqlalchemy import text
from app.db import engine

with engine.connect() as conn:
    result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"))
    print([row[0] for row in result])
