#!/usr/bin/env python3
"""biblioteca_fh.py 0.1 · laboratorio (24/11/2026) · carga en Turso la biblioteca FiberHome que exporta el PM.

Pedido de Nicolás (24/11): «pedile la base que te la dé y vos sumala a Turso». La fuente de verdad es la base del PM
(horizon-msyer). Acá solo se carga una copia de solo lectura para los motores de Loki, en tablas propias (DEC-1124a):
  fh_prod · fh_spec · fh_ficha_dato · fh_articulo · fh_pdf · fh_indice · fh_homologacion · fh_vocabulario · fh_cargas
(la vista fh_buscar, alias → producto, se arma cuando llegue la primera exportación y se conozcan las columnas).
Entrada: una carpeta biblioteca_FH_AAAA-MM-DD/ con prod.jsonl, prod_spec.jsonl, ficha_dato.jsonl, prod_articulo.jsonl,
prod_pdf.jsonl, homologacion.jsonl (o .csv con encabezado), indice.json, vocabulario.json y manifiesto.json
({origen, exportado, commit, tablas: {nombre: {filas, sha256}}}).
Controles: cada archivo tiene que coincidir con el manifiesto en filas y sha256; si uno no cierra, no se carga nada.
Nunca carga precios ni stock: se descartan las columnas cuyo nombre los nombra (eso entra por Finnegans y config/stock).
Cada carga reemplaza entera la anterior y queda registrada en fh_cargas.
Uso: python3 -I laboratorio/biblioteca_fh.py cargar CARPETA · verificar CARPETA · --autotest
"""
import csv, datetime as D, hashlib, importlib.util, io, json, os, re, sys, tempfile

VERSION = 'biblioteca_fh 0.1 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
TABLAS = {'prod': 'fh_prod', 'prod_spec': 'fh_spec', 'ficha_dato': 'fh_ficha_dato', 'prod_articulo': 'fh_articulo',
          'prod_pdf': 'fh_pdf', 'homologacion': 'fh_homologacion'}
PROHIBIDO = re.compile(r'precio|price|costo|cost|stock|lista_?usd|isp\b', re.I)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def leer_tabla(carpeta, nombre):
    for ext in ('jsonl', 'csv'):
        p = os.path.join(carpeta, f'{nombre}.{ext}')
        if os.path.exists(p):
            b = open(p, 'rb').read()
            t = b.decode('utf-8-sig')
            filas = ([json.loads(l) for l in t.splitlines() if l.strip()] if ext == 'jsonl'
                     else list(csv.DictReader(io.StringIO(t))))
            return filas, sha(b), f'{nombre}.{ext}'
    return None, None, None


def leer_json(carpeta, nombre):
    p = os.path.join(carpeta, f'{nombre}.json')
    if not os.path.exists(p):
        return None, None
    b = open(p, 'rb').read()
    return json.loads(b.decode('utf-8-sig')), sha(b)


def verificar(carpeta):
    """Devuelve (datos, problemas). datos = {nombre: filas}."""
    man, _ = leer_json(carpeta, 'manifiesto')
    if not man:
        return None, ['falta manifiesto.json']
    tab = man.get('tablas') or {}
    datos, prob = {}, []
    for nombre in list(TABLAS) + ['indice', 'vocabulario']:
        if nombre in ('indice', 'vocabulario'):
            d, h = leer_json(carpeta, nombre)
            filas = (d if isinstance(d, list) else [dict(clave=k, **(v if isinstance(v, dict) else {'valor': v})) for k, v in (d or {}).items()]) if d is not None else None
        else:
            filas, h, _ = leer_tabla(carpeta, nombre)
        if filas is None:
            if nombre in tab:
                prob.append(f'{nombre}: está en el manifiesto y falta el archivo')
            continue
        m = tab.get(nombre)
        if not m:
            prob.append(f'{nombre}: el archivo no está en el manifiesto')
            continue
        if m.get('sha256') and m['sha256'] != h:
            prob.append(f'{nombre}: sha256 distinto del manifiesto')
        if m.get('filas') is not None and int(m['filas']) != len(filas):
            prob.append(f'{nombre}: {len(filas)} filas y el manifiesto dice {m["filas"]}')
        datos[nombre] = filas
    return dict(manifiesto=man, datos=datos), prob


def limpiar(filas):
    cols, fuera = [], set()
    for f in filas:
        for k in f:
            if PROHIBIDO.search(k):
                fuera.add(k)
            elif k not in cols:
                cols.append(k)
    norm = lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
    return cols, [[norm(f.get(c)) for c in cols] for f in filas], sorted(fuera)


def sentencias(res):
    q, info = [], {}
    nombres = dict(TABLAS, indice='fh_indice', vocabulario='fh_vocabulario')
    for nombre, filas in res['datos'].items():
        t = nombres[nombre]
        cols, vals, fuera = limpiar(filas)
        info[t] = dict(filas=len(vals), columnas=len(cols), descartadas=fuera)
        q.append((f'DROP TABLE IF EXISTS {t}', []))
        if not cols:
            continue
        q.append((f'CREATE TABLE {t}(' + ', '.join(f'"{c}"' for c in cols) + ')', []))
        q += [(f'INSERT INTO {t} VALUES(' + ','.join('?' * len(cols)) + ')', v) for v in vals]
    return q, info


def autotest():
    with tempfile.TemporaryDirectory() as d:
        w = lambda n, s: open(os.path.join(d, n), 'w', encoding='utf-8').write(s)
        prod = '{"id": 1183, "nombre": "Caja NAP FH Preconectorizada 1x8", "precio_isp": 38.3}\n{"id": 1213, "nombre": "FitDP-420A"}\n'
        idx = json.dumps({'nap 1x8': {'prod': 1183}, 'caja preco': {'pregunta': [1339, 1337, 1338, 1340]}})
        w('prod.jsonl', prod); w('indice.json', idx)
        man = {'origen': 'prueba', 'tablas': {'prod': {'filas': 2, 'sha256': sha(prod.encode())}, 'indice': {'filas': 2, 'sha256': sha(idx.encode())}}}
        w('manifiesto.json', json.dumps(man))
        res, prob = verificar(d)
        q, info = sentencias(res)
        w('prod.jsonl', prod + '{"id": 9}\n')
        _, prob2 = verificar(d)
    casos = [
        ('manifiesto que cierra: sin problemas', prob == []),
        ('nunca carga precios', 'precio_isp' in info['fh_prod']['descartadas'] and all('precio' not in s for s, _ in q)),
        ('índice como tabla clave → datos', info['fh_indice']['filas'] == 2),
        ('archivo cambiado: falla filas y sha256', len(prob2) == 2),
    ]
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    k = sum(x for _, x in casos)
    print(f'autotest biblioteca_fh: {k}/{len(casos)}')
    return 0 if k == len(casos) else 1


def loki(ruta):
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    if a[:1] in (['cargar'], ['verificar']) and len(a) > 1:
        res, prob = verificar(a[1])
        if prob or not res:
            print('FALLA · no se carga nada:\n  ' + '\n  '.join(prob))
            sys.exit(1)
        q, info = sentencias(res)
        print(json.dumps(info, ensure_ascii=False, indent=1))
        if a[0] == 'cargar':
            db = loki(os.path.join(AQUI, '..', 'loki', 'loki_sql.py')).conectar()
            for i in range(0, len(q), 400):
                db.run(q[i:i + 400])
            man = res['manifiesto']
            db.run([('CREATE TABLE IF NOT EXISTS fh_cargas(cargado, version, origen, exportado, commit_pm, tablas)', []),
                    ('INSERT INTO fh_cargas VALUES(?,?,?,?,?,?)', [D.datetime.now(D.timezone.utc).isoformat(timespec='seconds'), VERSION,
                                                                    man.get('origen'), man.get('exportado'), man.get('commit'), json.dumps(info, ensure_ascii=False)])])
            db.close()
            print('RESUMEN cargada')
        sys.exit(0)
    print(__doc__)
