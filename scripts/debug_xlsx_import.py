import os
import sys
from app.xlsx_import.importer import read_header, _iter_all_rows

if len(sys.argv) != 2:
    print("Usage: python debug_xlsx_import.py <path-to-xlsx>")
    sys.exit(1)

path = sys.argv[1]
print("HEADER:")
cols = read_header(path)
print(cols)

print("ROWS:")
for i, row in enumerate(_iter_all_rows([path], cols), start=1):
    print(i, row)
    if i >= 20:
        break
