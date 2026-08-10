import os
import tempfile
from fastapi.testclient import TestClient
from openpyxl import Workbook
from app.main import app
from app.db import engine

client = TestClient(app)

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, 'test.xlsx')
    wb = Workbook()
    ws = wb.active
    ws.append(['name', 'value'])
    ws.append(['Alice', '1'])
    ws.append(['Bob', '2'])
    wb.save(path)

    with open(path, 'rb') as f:
        response = client.post('/xlsx/import', files={'files': ('test.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    print('response', response.status_code, response.json())
    table_name = response.json()['table_name']
    status = client.get(f'/xlsx/status/{table_name}')
    print('status1', status.status_code, status.json())
