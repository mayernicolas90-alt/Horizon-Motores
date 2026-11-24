#!/usr/bin/env python3
"""portada.py 0.1 · motor Portada del datacenter (24/11/2026, DEC-1124a/b). Solo biblioteca estándar.

Los 10 del día para la portada del CRM, en una sola lista ordenada por el puntaje de cierre CON monto (decisión de Nicolás 24/11).
Cada fila lleva su tipo de venta y en la lista tienen que aparecer los dos:
  · Rápida: ONT/ONU y recompras (todas sus cotizaciones abiertas son ONT/ONU, o muestra ONT, o le toca reponer sin cotización)
  · Consultiva: cable, OLT, ópticas y proyectos (todo lo demás)
Si en los 10 de mayor puntaje falta uno de los dos tipos, entran los mejores de ese tipo hasta tener MINIMO por tipo (si existen).
Calificación (como el Sales Engine del CRM): elegible hoy, sin «sin fondos», y puntaje ≥ 35 o cotización enviada o muestra activa
o le toca reponer; como máximo 2 prospectos nuevos (sin contacto). Las cuentas que no se trabajan ya vienen sin puntaje (Cuentas).

Lee pun_fichas (Puntaje), rec_cliente (Recompra) y la copia del CRM (crm). Escribe por_dia.
Uso (python3 -I): portada.py --contrato · portada.py --autotest · portada.py correr [--loki ruta] [--hoy AAAA-MM-DD] · portada.py simular
"""
import datetime as D, importlib.util, json, os, re, sys

VERSION = 'portada 0.1 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
TOTAL, MINIMO = 10, 3
CONTRATO = {'id': 'portada', 'nombre': 'Portada', 'disparo': 'loki', 'lee': ['pun_fichas', 'rec_cliente', 'crm'], 'escribe': ['por_dia'],
            'que_hace': 'Los 10 del día: una sola lista por puntaje con monto, con los dos tipos de venta (rápida y consultiva).'}
COLS = ['puesto', 'crm_id', 'empresa', 'tipo', 's', 's_sin_monto', 'valor_en_juego', 'motivo', 'accion', 'proxima_fecha', 'calculado']
ONU = re.compile(r'\b(ont|onu)\b|ont\s*/\s*onu|hg6\d{3}|an5506|eg8\d{3}|hs8\d{3}', re.I)
MACTIVA = {'pedida', 'sin_retirar', 'enviada', 'prueba'}
FUERA = {'rechazada', 'cancelada', 'perdida', 'entregada', 'aceptada'}


def tipo(o, cots, mues, toca):
    abiertas = [c for c in cots if c.get('oportunidadId') == o['id'] and not c.get('archivada') and str(c.get('estado') or '').lower() not in FUERA]
    if abiertas:
        return 'rapida' if all(ONU.search(str(c.get('familia') or '')) or ONU.search(' '.join(str(i.get('articulo') or '') for i in c.get('items') or []))
                                for c in abiertas) else 'consultiva'
    ms = [m for m in mues if m.get('oportunidadId') == o['id'] and m.get('estado') in MACTIVA]
    if ms:
        return 'rapida' if all(ONU.search(str(m.get('productos') or '')) for m in ms) else 'consultiva'
    return 'rapida' if toca else 'consultiva'



def calcular(pun, fichas, cots, mues, rec, hoy):
    """pun: filas de pun_fichas · fichas/cots/mues: documentos del CRM · rec: {cuit: (estado, estado_global)}."""
    ops = {o['id']: o for o in fichas}
    cand = []
    for p in pun:
        o = ops.get(p['crm_id'])
        if not o or not p['elegible'] or p['s'] is None or p['funding'] == 'sin_fondos':
            continue
        est, glo = rec.get(p['cuit'] or '', (None, None))
        toca = est in ('Le toca', 'Atrasado') or glo in ('toca', 'atrasado')
        cotiza = any(c.get('oportunidadId') == o['id'] and str(c.get('estado') or '') in ('enviada', 'borrador') and not c.get('archivada') for c in cots)
        muestra = any(m.get('oportunidadId') == o['id'] and m.get('estado') in MACTIVA for m in mues)
        if not (p['s'] >= 35 or cotiza or muestra or toca):
            continue
        nuevo = o.get('etapa') == 'prospecto' and not o.get('ultimoContacto')
        cand.append(dict(p=p, o=o, tipo=tipo(o, cots, mues, toca), nuevo=nuevo))
    cand.sort(key=lambda x: (-x['p']['s'], -(x['p']['valor_en_juego'] or 0), x['p']['empresa']))
    pick, nuevos = [], 0
    def puede(x):
        return not x['nuevo'] or nuevos < 2
    for x in cand:
        if len(pick) >= TOTAL:
            break
        if puede(x):
            pick.append(x); nuevos += x['nuevo']
    for t in ('rapida', 'consultiva'):
        faltan = MINIMO - sum(x['tipo'] == t for x in pick)
        extra = [x for x in cand if x['tipo'] == t and x not in pick and puede(x)][:max(0, faltan)]
        for x in extra:
            # sale el de menor puntaje del tipo que sobra, sin bajar al otro tipo de su mínimo
            otro = [y for y in pick if y['tipo'] != t]
            if len(pick) >= TOTAL and len(otro) > MINIMO:
                pick.remove(otro[-1])
            if len(pick) < TOTAL:
                pick.append(x); nuevos += x['nuevo']
    pick.sort(key=lambda x: (-x['p']['s'], -(x['p']['valor_en_juego'] or 0), x['p']['empresa']))
    filas = []
    for i, x in enumerate(pick, 1):
        r = [m for m in json.loads(x['p']['razones'] or '[]') if not m.startswith('Fondos sin')][:3]
        filas.append(dict(puesto=i, crm_id=x['o']['id'], empresa=x['p']['empresa'], tipo=x['tipo'], s=x['p']['s'], s_sin_monto=x['p']['s_sin_monto'],
                          valor_en_juego=x['p']['valor_en_juego'], motivo=' · '.join(r), accion=x['o'].get('proximaAccion') or '',
                          proxima_fecha=x['o'].get('proximaFecha') or None, calculado=hoy))
    return filas


def loki(ruta=None):
    ruta = ruta or os.path.join(AQUI, 'loki_sql.py')
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def leer(db):
    cols, filas = db.run([('SELECT * FROM pun_fichas', [])])[0]
    pun = [dict(zip(cols, f)) for f in filas]
    docs = {'oportunidades': [], 'cotizaciones': [], 'muestras': []}
    for col, i, data in db.run([("SELECT coleccion, id, data FROM crm WHERE coleccion IN ('oportunidades','cotizaciones','muestras')", [])])[0][1]:
        d = json.loads(data or '{}'); d['id'] = i; docs[col].append(d)
    rec = {r[0]: (r[1], r[2]) for r in db.run([('SELECT cuit, estado, estado_global FROM rec_cliente', [])])[0][1]}
    return pun, docs['oportunidades'], docs['cotizaciones'], docs['muestras'], rec


def escribir(db, filas):
    db.run([('DROP TABLE IF EXISTS por_dia', []), ('CREATE TABLE por_dia(' + ', '.join(COLS) + ')', [])]
           + [('INSERT INTO por_dia VALUES(' + ','.join('?' * len(COLS)) + ')', [f[c] for c in COLS]) for f in filas])


# ---------------------------------------------------------------- autotest (sin datos reales)
def autotest():
    hoy = '2026-11-24'
    P = lambda i, s, **k: dict(dict(crm_id=i, cuit='30' + i, empresa='E' + i, elegible=1, s=s, s_sin_monto=s, valor_en_juego=0, funding='sin_definir', razones='[]'), **k)
    O = lambda i, **k: dict(dict(id=i, etapa='cotizado', ultimoContacto='2026-11-01', proximaAccion='Llamar'), **k)
    C = lambda op, fam: dict(oportunidadId=op, estado='enviada', familia=fam)
    # 12 consultivas con puntaje alto y 3 rápidas con puntaje bajo
    pun = [P(f'c{i}', 90 - i) for i in range(12)] + [P(f'r{i}', 40 - i) for i in range(3)] + [P('sf', 99, funding='sin_fondos'), P('ne', 98, elegible=0),
           P('p1', 97), P('p2', 96), P('p3', 95), P('bajo', 10)]
    fichas = [O(x['crm_id']) for x in pun] + []
    for f in fichas:
        if f['id'] in ('p1', 'p2', 'p3'):
            f.update(etapa='prospecto', ultimoContacto='')
    cots = [C(f'c{i}', 'Cables de fibra') for i in range(12)] + [C(f'r{i}', 'ONT / ONU') for i in range(3)] + [C(x, 'OLT y placas') for x in ('p1', 'p2', 'p3')]
    filas = calcular(pun, fichas, cots, [], {}, hoy)
    ids = [f['crm_id'] for f in filas]
    tipos = [f['tipo'] for f in filas]
    casos = [
        ('una sola lista de 10', len(filas) == 10 and [f['puesto'] for f in filas] == list(range(1, 11))),
        ('ordenada por puntaje con monto', [f['s'] for f in filas] == sorted([f['s'] for f in filas], reverse=True)),
        ('aparecen los dos tipos de venta: mínimo 3 rápidas aunque tengan menos puntaje', tipos.count('rapida') == 3 and tipos.count('consultiva') == 7),
        ('sin fondos y no elegibles quedan afuera', 'sf' not in ids and 'ne' not in ids),
        ('como máximo 2 prospectos nuevos', sum(i in ids for i in ('p1', 'p2', 'p3')) == 2),
        ('puntaje bajo sin cotización ni recompra no califica', 'bajo' not in ids),
        ('le toca reponer sin cotización: rápida', tipo(O('x'), [], [], True) == 'rapida' and tipo(O('x'), [], [], False) == 'consultiva'),
    ]
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    ok = sum(1 for _, x in casos if x)
    print(f'autotest portada: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    hoy = a[a.index('--hoy') + 1] if '--hoy' in a else D.datetime.now(D.timezone(D.timedelta(hours=-3))).date().isoformat()
    if '--autotest' in a:
        sys.exit(autotest())
    if '--contrato' in a:
        print(json.dumps(dict(CONTRATO, version=VERSION), ensure_ascii=False))
        sys.exit(0)
    if a[:1] in (['correr'], ['simular']):
        db = loki(a[a.index('--loki') + 1] if '--loki' in a else None).conectar()
        filas = calcular(*leer(db), hoy)
        if a[0] == 'correr':
            escribir(db, filas)
        db.close()
        if a[0] == 'simular':
            print(json.dumps(filas, ensure_ascii=False))
        print('RESUMEN ' + json.dumps({'puestos': len(filas), 'rapidas': sum(f['tipo'] == 'rapida' for f in filas),
                                       'consultivas': sum(f['tipo'] == 'consultiva' for f in filas)}, ensure_ascii=False))
        sys.exit(0)
    print(__doc__)
