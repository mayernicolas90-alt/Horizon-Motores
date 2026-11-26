#!/usr/bin/env python3
"""equivalencias.py 1.0 · traduce el nombre que usa el cliente o Nicolás («GPHF C++», «preco 100», «1355») al código
del ERP que usa HIVE (productoid), para consultar stock y precio en vivo por código y no por texto (L-004 del PM:
la GPHF C++ figura como PCB GPCMM, 1355; buscada por nombre en HIVE da «sin_datos»).

Fuente de las equivalencias: los alias del PM (base horizon-msyer, SOLO LECTURA con pm_lectura.py) → su artículo de
lista → código. Control cruzado: el mismo código en el stock R8 de Loki (nombre, cantidad y fecha); si el nombre de
la lista y el del R8 no son el mismo producto, avisa (p. ej. «GPOA C++» con el código de la GPOA C+).

Uso (PC):  python -I -X utf8 %USERPROFILE%\\.loki\\conauth.py equivalencias.py "GPHF C++"
Sale un JSON corto: {consulta, estado: ok | ambiguo | sin_datos, candidatos[{codigo, nombre, nota, r8{...}, aviso}]}.
Con «ok» se consulta HIVE (consultar_stock / precio_producto) por `codigo`; HIVE manda. Si HIVE no lo trae, el R8
de acá es el respaldo, con su fecha. «ambiguo»: preguntar cuál. «sin_datos»: no inventar; decirlo.
"""
import json, os, re, sys, unicodedata

VERSION = '1.0'
GENERICAS = ('placa', 'huawei', 'fiberhome', 'pcb', 'hw', 'fh', 'zte', 'ont', 'onu', 'olt')


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '').lower())
    return re.sub(r'[^a-z0-9+]', '', ''.join(c for c in s if not unicodedata.combining(c)))


def variantes(texto):
    """Formas de escribir lo mismo, en orden de confianza: tal cual, con «plus», sin palabras genéricas."""
    v = [norm(texto)]
    v.append(v[0].replace('+', 'plus'))
    pal = [p for p in re.split(r'\s+', str(texto or '').strip()) if norm(p) not in GENERICAS]
    if pal:
        v.append(norm(' '.join(pal)))
        v.append(v[-1].replace('+', 'plus'))
    return [x for i, x in enumerate(v) if x and x not in v[:i]]


def resolver(pm, r8, texto):
    """pm(sql, args) y r8(sql, args) devuelven filas como dict. Sin red: el autotest les pasa bases en memoria."""
    filas, usada = [], None
    for v in variantes(texto):
        filas = pm('SELECT alias, clave, entrada, nombre, nota FROM alias WHERE alias = ?', [v])
        if filas:
            usada = v
            break
    if not filas and re.fullmatch(r'\d{3,6}', str(texto).strip()):
        filas = [dict(alias=texto, clave=None, entrada=None, nombre=None, nota='código escrito tal cual')]
        usada = 'codigo'
    if not filas:
        return dict(consulta=texto, estado='sin_datos', motivo='ningún alias del PM coincide; probar otra forma o el código', candidatos=[])
    cands = {}
    for f in filas:
        claves = [k for k in (f['clave'], f['entrada']) if k and str(k).startswith('lista:')]
        if usada == 'codigo':
            prods = pm('SELECT clave, codigo, nombre FROM producto WHERE codigo = ?', [str(texto).strip()])
        else:
            prods = [p for k in claves for p in pm('SELECT clave, codigo, nombre FROM producto WHERE clave = ?', [k])]
        if not prods:   # está en el catálogo del PM pero no en la lista: sin código de ERP
            cands.setdefault(('', f['entrada']), dict(codigo='', nombre=f['nombre'], nota=f['nota'] or '', aviso='en el PM sin código de ERP: HIVE no lo puede buscar'))
        for p in prods:
            cands.setdefault((p['codigo'] or '', p['clave']), dict(codigo=p['codigo'] or '', nombre=p['nombre'], nota=f['nota'] or '',
                                                                aviso='' if p['codigo'] else 'en la lista sin código de ERP: HIVE no lo puede buscar'))
    out = list({(c['codigo'] or c['nombre']): c for c in cands.values()}.values())   # un candidato por código
    con_codigo = [c for c in out if c['codigo']]
    if con_codigo and len(out) > len(con_codigo):
        out = con_codigo       # si hay uno con código, los que no tienen código sobran (son la misma ficha del catálogo)
    for c in out:
        if not c['codigo']:
            c['r8'] = None
            continue
        st = r8('SELECT productoid, producto, SUM(CAST(stock AS REAL)) AS stock FROM stock WHERE productoid = ? GROUP BY productoid, producto', [c['codigo']])
        corte = r8("SELECT corte FROM cargas WHERE fuente = 'R8'", [])
        c['r8'] = dict(nombre=st[0]['producto'], stock=float(st[0]['stock'] or 0), corte=(corte[0]['corte'] if corte else None)) if st else None
        if st and norm(st[0]['producto']).replace('placa', '') != norm(c['nombre']).replace('placa', ''):
            c['aviso'] = (c['aviso'] + ' · ' if c['aviso'] else '') + f"el código {c['codigo']} en el R8 es «{st[0]['producto']}», no «{c['nombre']}»: confirmar el código"
    return dict(consulta=texto, estado='ok' if len(out) == 1 else 'ambiguo', candidatos=out)


def autotest():
    import sqlite3
    pm, lk = sqlite3.connect(':memory:'), sqlite3.connect(':memory:')
    for d in (pm, lk):
        d.row_factory = sqlite3.Row
    pm.executescript("""
      CREATE TABLE alias (alias, clave, entrada, nombre, nota); CREATE TABLE producto (clave, codigo, nombre);
      INSERT INTO alias VALUES ('gphfc++','lista:pcb-gpcmm','huawei:hw-gphf-cpp','Placa Huawei GPHF C++','= PCB GPCMM (H901)'),
        ('gpcmm','lista:pcb-gpcmm','huawei:hw-gphf-cpp','Placa Huawei GPHF C++',''),
        ('gpufc+',NULL,'lista:placa-huawei-gpuf-c','Placa Huawei GPUF C+',''),
        ('gpoac++',NULL,'lista:placa-gpoa-c#1123','Placa GPOA C++',''),
        ('an6000',NULL,'lista:a','AN6000-2',''),('an6000',NULL,'lista:b','AN6000-7','');
      INSERT INTO producto VALUES ('lista:pcb-gpcmm','1355','PCB GPCMM'),('lista:placa-huawei-gpuf-c','','Placa Huawei GPUF C+'),
        ('lista:placa-gpoa-c#1123','1123','Placa GPOA C++'),('lista:a','1001','OLT AN6000-2'),('lista:b','1002','OLT AN6000-7');""")
    lk.executescript("""
      CREATE TABLE stock (productoid, producto, stock); CREATE TABLE cargas (fuente, corte);
      INSERT INTO stock VALUES ('1355','PCB GPCMM',31),('1123','Placa GPOA C+',0),('1001','OLT AN6000-2',2);
      INSERT INTO cargas VALUES ('R8','2026-11-25');""")
    q = lambda db: (lambda sql, a: [dict(x) for x in db.execute(sql, a)])
    r = lambda t: resolver(q(pm), q(lk), t)
    a, b, c, d, e, f = r('GPHF C++'), r('Placa Huawei GPHF C++'), r('GPUF C+'), r('GPOA C++'), r('AN6000'), r('nada que ver')
    casos = [
        ('GPHF C++ → 1355 con stock R8 31', a['estado'] == 'ok' and a['candidatos'][0]['codigo'] == '1355' and a['candidatos'][0]['r8']['stock'] == 31),
        ('palabras genéricas no molestan', b['estado'] == 'ok' and b['candidatos'][0]['codigo'] == '1355'),
        ('en la lista sin código: lo avisa', c['estado'] == 'ok' and c['candidatos'][0]['codigo'] == '' and 'sin código' in c['candidatos'][0]['aviso']),
        ('código que en el R8 es otro producto: avisa', 'confirmar el código' in d['candidatos'][0]['aviso']),
        ('dos productos con el mismo alias: ambiguo', e['estado'] == 'ambiguo' and len(e['candidatos']) == 2),
        ('sin alias: sin_datos', f['estado'] == 'sin_datos'),
        ('código escrito tal cual', r('1355')['candidatos'][0]['nombre'] == 'PCB GPCMM'),
        ('norm saca acentos y espacios, deja +', norm('Placa Óptica C++') == 'placaopticac++'),
    ]
    mal = [n for n, ok in casos if not ok]
    for n, ok in casos:
        print(('PASA ' if ok else 'FALLA') + ' · ' + n)
    print(f'autotest equivalencias: {len(casos) - len(mal)}/{len(casos)} ' + ('PASA' if not mal else 'FALLA'))
    return 1 if mal else 0


def main(a):
    if a[:1] == ['--autotest']:
        return autotest()
    if len(a) != 1:
        print(__doc__); return 2
    aqui = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, aqui)
    sys.path.insert(1, os.path.join(os.environ.get('USERPROFILE', ''), '.loki'))   # pm_lectura (token del PM) vive en .loki
    import pm_lectura
    from bitacora2 import turso
    lit = lambda x: "'" + str(x).replace("'", "''") + "'"     # pm_lectura no tiene parámetros: literal SQL escapado
    pm = lambda sql, args: pm_lectura.consulta(sql.replace('?', '{}').format(*[lit(x) for x in args]))
    print(json.dumps(resolver(pm, lambda sql, args: turso(sql, args), a[0]), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
