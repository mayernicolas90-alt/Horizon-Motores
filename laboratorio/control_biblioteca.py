#!/usr/bin/env python3
"""control_biblioteca.py 0.1 · controles cruzados sobre la copia de la biblioteca FiberHome (tablas fh_* en Turso).

Lee solo Turso de Loki (fh_* que carga biblioteca_fh.py desde la base del PM, y limpia_compras_firmes). No escribe nada.
Controles (AVISO = dato para que el PM corrija; nunca bloquea a los motores):
  C1 alias que apuntan a una entrada de lista que no existe
  C2 producto ↔ artículo (prod_articulo) con clave de lista que no existe
  C3 prod_articulo con producto inexistente · C4 datos técnicos y fichas huérfanos
  C5 productos FiberHome vendidos (Finnegans) sin entrada con el mismo nombre en la lista
  C6 pedidos de prueba: cada texto tiene que encontrar el código esperado en la lista (por nombre o alias)
Uso: python3 -I laboratorio/control_biblioteca.py [--detalle]
"""
import importlib.util, os, re, sys, unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
# pedidos reales con el código que tiene que aparecer como opción (resultado escrito antes de probar)
PEDIDOS = [('caja preco 1x8', '1183'), ('nap 1x8', '1183'), ('420a', '1213'), ('drop', '1179')]


def n(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


SIN = {'caja': 'nap', 'preco': 'preconectorizada'}


def candidatos(texto, prod, ali):
    ws = [SIN.get(w, w) for w in n(texto).split()]
    por_nombre = {c for _, c, nm in prod if all(w in n(nm).replace(' ', '') or w in n(nm) for w in ws if w != 'nap') and
                  (('nap' not in ws) or 'nap' in n(nm))}
    por_alias = {a[1] for a in ali if a[1] and n(a[0]).replace(' ', '') == n(texto).replace(' ', '')}
    return por_nombre | por_alias


def main(a):
    sp = importlib.util.spec_from_file_location('l', os.path.join(AQUI, '..', 'loki', 'loki_sql.py'))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    db = m.conectar(); q = lambda s: db.run([(s, [])])[0][1]
    prod = q('SELECT clave, codigo, nombre FROM fh_producto'); claves = {k for k, _, _ in prod}
    ali = q('SELECT alias, clave, entrada, nombre FROM fh_alias')
    art = q('SELECT prod_id, clave_lista FROM fh_articulo'); fid = {r[0] for r in q('SELECT id FROM fh_prod')}
    fin = q("SELECT producto FROM limpia_compras_firmes WHERE marca LIKE '%iber%ome%' GROUP BY 1")
    huer = q('SELECT (SELECT count(*) FROM fh_spec WHERE prod_id NOT IN (SELECT id FROM fh_prod)) + '
             '(SELECT count(*) FROM fh_ficha_dato WHERE prod_id NOT IN (SELECT id FROM fh_prod))')[0][0]
    db.close()
    nombres = {n(x[2]) for x in prod}
    r = [('C1 alias a entrada de lista inexistente', [x[0] for x in ali if str(x[2] or '').startswith('lista:') and x[2] not in claves]),
         ('C2 producto↔artículo con clave de lista inexistente', [f'{x[0]} → {x[1]}' for x in art if x[1] and x[1] not in claves]),
         ('C3 artículo con producto inexistente', [x[0] for x in art if x[0] not in fid]),
         ('C4 datos técnicos o fichas huérfanos', ['huérfanos'] * int(huer or 0)),
         ('C5 FiberHome vendido sin entrada en la lista', [p for (p,) in fin if n(p) not in nombres])]
    r += [(f'C6 pedido «{t}» → {c}', [] if c in candidatos(t, prod, ali) else [f'no aparece {c}']) for t, c in PEDIDOS]
    mal = 0
    for nombre, xs in r:
        print(f"{'PASA ' if not xs else 'AVISO'} {nombre}: {len(xs)}" + (f" · {', '.join(map(str, xs[:6]))}" if xs and '--detalle' in a else ''))
        mal += bool(xs)
    print(f'RESUMEN {len(r) - mal}/{len(r)} sin observaciones')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
