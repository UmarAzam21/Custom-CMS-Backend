from app.db import engine

conn = engine.raw_connection()
try:
    cur = conn.cursor()
    cur.execute('SELECT table_name, status, row_count, processed_rows, source_file, error_message, created_at, activated_at FROM dataset_versions ORDER BY created_at DESC LIMIT 20')
    for row in cur.fetchall():
        print(row)
    cur.close()
finally:
    conn.close()
