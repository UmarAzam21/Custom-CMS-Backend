import os
import tempfile
from openpyxl import Workbook
from app.xlsx_import.importer import read_header, create_import_table, load_rows_into_table, new_table_name
from app.db import engine

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, 'test.xlsx')
    wb = Workbook()
    ws = wb.active
    ws.append(['name', 'value'])
    ws.append(['Alice', '1'])
    ws.append(['Bob', '2'])
    wb.save(path)

    cols = read_header(path)
    table = new_table_name()
    print('table', table)
    print('cols', cols)

    create_import_table(table, cols)
    rows = load_rows_into_table(table, cols, [path], batch_size=1)
    print('loaded rows', rows)

    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT count(*) FROM "{table}"')
        print('count', cur.fetchone()[0])
        cur.close()
    finally:
        conn.close()
