from app.db import engine  # <-- adjust if your engine var is named differently


def init_control_tables():
    """Creates the metadata table that tracks every import and which one is live."""
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_versions (
                id SERIAL PRIMARY KEY,
                table_name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'importing',
                row_count BIGINT DEFAULT 0,
                processed_rows BIGINT DEFAULT 0,
                source_file TEXT,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                activated_at TIMESTAMPTZ
            )
            """
        )
        # backward-compatible if the table already existed from an earlier version
        cur.execute(
            "ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS processed_rows BIGINT DEFAULT 0"
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def set_status(table_name: str, status: str, **fields):
    """Updates status plus any extra columns, e.g. set_status(t, 'failed', error_message='...')."""
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        set_parts = ["status = %s"]
        values = [status]
        for key, value in fields.items():
            set_parts.append(f"{key} = %s")
            values.append(value)
        values.append(table_name)
        cur.execute(
            f"UPDATE dataset_versions SET {', '.join(set_parts)} WHERE table_name = %s",
            values,
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def update_progress(table_name: str, processed_rows: int):
    """Called frequently during a big import so /xlsx/status shows live progress."""
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dataset_versions SET processed_rows = %s WHERE table_name = %s",
            (processed_rows, table_name),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()