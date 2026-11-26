"""volcar.py 1.0 · respaldo local de la base de Loki: vuelca Turso horizon-nicom90 a un SQLite (solo LEE Turso).
Uso (PC):   python -I -X utf8 %USERPROFILE%\\.loki\\conauth.py volcar.py LOKI_SQL.py SALIDA.sqlite
Deja SALIDA.sqlite (tablas, vistas e índices) y SALIDA.sqlite.conteos.json, y controla que cada tabla tenga las mismas
filas que en Turso (imprime control PASA / FALLA). El respaldo tiene datos de clientes (D10): privado, no se comparte.
Para leerlo sin Turso: LOKI_SQL_LOCAL=SALIDA.sqlite python -I loki_sql.py estado.
1.0 (26/11, hacelo de Nicolás): venía del respaldo de la nube del 26/11; se suma el uso y no pisa una salida existente."""
import importlib.util, sqlite3, sys, json, os

if len(sys.argv) != 3:
    sys.exit(__doc__)
spec = importlib.util.spec_from_file_location('loki_sql', sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
out = sys.argv[2]
if os.path.exists(out):
    sys.exit(f'FALLA {out} ya existe: elegir otro nombre (el respaldo no pisa otro respaldo)')
db = m.conectar()
lo = sqlite3.connect(out)
objs = m.q(db, "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_litestream%' ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, name")
res = {}
for o in [x for x in objs if x['type'] == 'table']:
    lo.execute(o['sql'])
    cols = [c['name'] for c in m.q(db, f"PRAGMA table_info(\"{o['name']}\")")]
    n, off = 0, 0
    while True:
        rows = m.q(db, f"SELECT * FROM \"{o['name']}\" LIMIT 2000 OFFSET {off}")
        if not rows: break
        lo.executemany(f"INSERT INTO \"{o['name']}\" ({','.join(chr(34)+c+chr(34) for c in cols)}) VALUES ({','.join('?'*len(cols))})",
                       [[r.get(c) for c in cols] for r in rows])
        n += len(rows); off += 2000
        if len(rows) < 2000: break
    res[o['name']] = n
for o in [x for x in objs if x['type'] != 'table']:
    try: lo.execute(o['sql'])
    except Exception as e: print('AVISO', o['type'], o['name'], e)
lo.commit()
# control: conteos iguales
mal = [t for t, n in res.items() if lo.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] != m.q(db, f'SELECT COUNT(*) n FROM "{t}"')[0]['n']]
lo.close()
print(json.dumps({'tablas': len(res), 'filas': sum(res.values()), 'vistas_indices': len(objs) - len(res), 'control': 'FALLA ' + str(mal) if mal else 'PASA'}))
json.dump(res, open(out + '.conteos.json', 'w'), indent=1)
