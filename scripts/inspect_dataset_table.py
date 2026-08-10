from app.db import engine

TABLE = 'dataset_1786344712581'
conn = engine.raw_connection()
try:
    cur = conn.cursor()
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = %s)", (TABLE,))
    exists = cur.fetchone()[0]
    print('table exists', exists)
    if exists:
        cur.execute(f'SELECT count(*) FROM "{TABLE}"')
        print('count', cur.fetchone()[0])
    cur.close()
finally:
    conn.close()
