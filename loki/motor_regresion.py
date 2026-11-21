"""Corre un motor.py sobre los renglones de las cotizaciones del CRM + pedidos sueltos y guarda el resultado."""
import sys, json, importlib.util
def cargar(p, n):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
mot = cargar(sys.argv[1], 'motor_x')
ls = mot._cargar_loki_sql()
db = ls.conectar()
cat, corte = mot.catalogo(db, ls.q)
filas = ls.q(db, "SELECT cotizacion_id, n, articulo, descripcion, codigo FROM crm_cotizacion_item")
db.close()
out = {}
for f in filas:
    for tipo, txt in (('art', f['articulo']), ('desc', f['descripcion'])):
        if not txt: continue
        r = mot.cruzar(cat, str(txt))
        out[f"{f['cotizacion_id']}#{f['n']}#{tipo}"] = {'txt': txt, 'est': r['estado'], 'item': (r['item'] or {}).get('id'),
            'ops': [o[0]['id'] for o in r['opciones']]}
for t in sys.argv[3:]:
    r = mot.cruzar(cat, t)
    out['libre#' + t] = {'txt': t, 'est': r['estado'], 'item': (r['item'] or {}).get('id'), 'ops': [o[0]['id'] for o in r['opciones']]}
json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(len(out), 'renglones', {e: sum(1 for v in out.values() if v['est'] == e) for e in ('CUMPLE','OPCIONES','SIN PRECIO','NO TENEMOS')})
