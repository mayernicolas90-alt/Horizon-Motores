#!/usr/bin/env python3
"""cola_dia.py 0.1 · laboratorio (24/11/2026) · la cola diaria de seguimiento (5 cuentas) para la apertura de Loki.

Acordado en el buzón (para_PM_2026-11-24_l/_m · para_CRM_2026-11-24_p/_q). Regla de 5:
  2 cotizaciones vivas (primero las de revisión vencida, por monto) · 1 recompra (red en prueba, si no «más reciente»)
  1 cuenta que compra ONT FiberHome sin la OLT relevada en la ficha · 1 lead que respondió hace poco sin próximo paso
Cada fila: cuenta, motivo, pregunta concreta y dato a cargar al volver. Sin textos armados (pedido de Nicolás).
No repite la misma cuenta con la misma pregunta del día anterior. Las cuentas excluidas (no prospectar, otro
vendedor, archivada) y las fichas archivadas no entran. Las ganadas no ocupan lugar de cotización ni de lead
(su fecha vencida es posventa), pero sí entran como recompra y base FH.
Lee crm (copia de 5SPm), red_pred, cue_cuentas, limpia_compras_firmes. Escribe solo cola_dia (DEC-1124a).
La muestra `abrir` (sesión Loki); el resultado de cada contacto se carga en 5SPm con el «hacelo».
Uso: python3 -I laboratorio/cola_dia.py correr [--hoy AAAA-MM-DD] · simular · --autotest
    Recompra: no se llama al que acaba de comprar. Entra recién cuando pasaron 15 días y el 70 % de su ciclo
    (pedido de Nicolás, 24/11: no llamar por recompra a quien acaba de comprar).
"""
import datetime as D, importlib.util, json, os, re, sys

VERSION = 'cola_dia 0.1 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
COLS = ['dia', 'puesto', 'bloque', 'crm_id', 'cuenta', 'motivo', 'pregunta', 'dato_a_cargar', 'version', 'calculado']
ABIERTAS = {'enviada', 'espera_aprobacion'}
CERRADAS = {'ganado', 'perdido', 'archivado', 'descartado'}
EXCL = ('no_prospectar', 'otro_vendedor', 'archivada')
dig = lambda s: re.sub(r'\D', '', str(s or ''))


def fd(s):
    return D.date.fromisoformat(str(s)[:10]) if str(s or '')[:4].isdigit() else None


def pregunta_cot(fam, emp, ayer):
    fam = fam.lower()
    if 'telviso' in emp.lower():
        opciones = ['¿Cómo viene la prueba en calle y para cuándo la compra?', '¿Qué les falta validar para pasar a compra?']
    elif 'cable' in fam or 'fibra' in fam:
        opciones = ['¿La traba es precio, plazo o especificación? Si es precio: ¿contra qué marca y a cuánto?',
                    '¿Les sirve una entrega parcial o un precio por volumen para destrabarlo?']
    elif 'olt' in fam:
        opciones = ['¿Ya está aprobado el presupuesto? ¿Quién firma y para cuándo?', '¿Qué otra OLT están evaluando?']
    else:
        opciones = ['¿Sigue en pie? ¿La traba es precio, plazo o stock?', '¿Renuevo la misma cotización con nueva fecha?']
    return next((q for q in opciones if q not in ayer), opciones[-1])


def calcular(crm, excl_cuit, excl_id, red, fh_onu, hoy, ayer):
    """crm: {'oportunidades': {id: doc}, 'cotizaciones': {id: doc}} · red: [(cuit, puesto)] ordenado ·
    fh_onu: {cuit} que compraron ONT FH · ayer: {crm_id: {preguntas}}."""
    O, C = crm['oportunidades'], crm['cotizaciones']
    ok = lambda k, o: (k not in excl_id and dig(o.get('cuit')) not in excl_cuit and not o.get('archivada')
                       and not o.get('noProspectar') and o.get('etapa') not in CERRADAS)
    filas, usados = [], set()

    def add(bloque, k, o, motivo, preg, dato):
        if preg in ayer.get(k, set()):
            return False
        filas.append(dict(bloque=bloque, crm_id=k, cuenta=o.get('empresa') or k, motivo=motivo, pregunta=preg, dato_a_cargar=dato))
        usados.add(k)
        return True

    # 1) dos cotizaciones vivas
    por = {}
    for c in C.values():
        if str(c.get('estado')) in ABIERTAS and not c.get('archivada'):
            por.setdefault(c.get('oportunidadId'), []).append(c)
    cand = []
    for k, cs in por.items():
        o = O.get(k)
        if not o or not ok(k, o):
            continue
        fechas = [fd(c.get('revisionFecha')) or fd(c.get('vence')) for c in cs] + [fd(o.get('proximaFecha'))]
        rev = min([x for x in fechas if x] or [hoy])  # sin ninguna fecha cuenta como vencida hoy
        monto = sum(float(c.get('neto') or c.get('total') or 0) for c in cs)
        fam = ', '.join(sorted({str(c.get('familia') or '?') for c in cs}))
        cand.append((rev > hoy, -monto, k, o, cs, fam, rev, monto))
    n = 0
    for _, _, k, o, cs, fam, rev, monto in sorted(cand, key=lambda t: t[:3]):
        nums = ', '.join(str(c.get('numero') or '')[:12] for c in cs)
        if add('cotizacion', k, o, f'{nums} · {fam} · USD {monto:,.0f} neto · revisión {rev}', pregunta_cot(fam, o.get('empresa') or '', ayer.get(k, set())),
               'resultado (contestó / no / dato nuevo), motivo si se cae y próxima fecha'):
            n += 1
        if n == 2:
            break
    # para recompra y base FH sí entran las ganadas: el cliente que ya compró es justamente el que recompra
    ok_cli = lambda k, o: ok(k, dict(o, etapa=None if o.get('etapa') == 'ganado' else o.get('etapa')))
    cuit_op = {}
    for k, o in O.items():
        if dig(o.get('cuit')) and ok_cli(k, o):
            cuit_op.setdefault(dig(o['cuit']), k)
    # 2) una recompra
    for cuit, puesto in red:
        k = cuit_op.get(dig(cuit))
        if k and k not in usados and k not in por:
            if add('recompra', k, O[k], f'puesto {puesto} en la lista de recompra (red en prueba)',
                   '¿Cómo vienen de stock y para cuándo la próxima compra? ¿Cuántas?', 'fecha y cantidad estimadas de la próxima compra'):
                break
    # 3) una base FH sin OLT relevada
    for cuit in sorted(fh_onu):
        k = cuit_op.get(dig(cuit))
        if k and k not in usados and not str(O[k].get('marcaOlt') or '').strip():
            if add('base_fh', k, O[k], 'compra ONT FiberHome y la ficha no tiene la OLT', '¿Qué OLT tienen (marca y modelo)?',
                   'marcaOlt y modeloOlt en la ficha'):
                break
    # 4) un lead que respondió (contacto en los últimos 14 días, etapa temprana, sin próximo paso)
    leads = [(fd(o.get('ultimoContacto')), k, o) for k, o in O.items() if ok(k, o) and k not in usados
             and o.get('etapa') in ('prospecto', 'contactado') and fd(o.get('ultimoContacto'))
             and (hoy - fd(o['ultimoContacto'])).days <= 14 and not fd(o.get('proximaFecha'))]
    for _, k, o in sorted(leads, key=lambda t: t[0], reverse=True):
        if add('lead', k, o, f"respondió el {o['ultimoContacto'][:10]} y no tiene próximo paso",
               '¿Qué necesitan resolver y para cuándo? ¿Quién decide?', 'necesidad, decisor y próxima fecha'):
            break
    for i, f in enumerate(filas, 1):
        f.update(dia=hoy.isoformat(), puesto=i, version=VERSION)
    return filas


def autotest():
    hoy = D.date(2026, 11, 24)
    O = {'a': dict(empresa='A', etapa='cotizado', cuit='30-1'), 'b': dict(empresa='B', etapa='cotizado', cuit='30-2'),
         'c': dict(empresa='C', etapa='cotizado', cuit='30-3'), 'x': dict(empresa='X', etapa='cotizado', cuit='30-9'),
         'r': dict(empresa='R', etapa='contactado', cuit='30-4'), 'f': dict(empresa='F', etapa='contactado', cuit='30-5'),
         'l': dict(empresa='L', etapa='contactado', ultimoContacto='2026-11-20'), 'g': dict(empresa='G', etapa='ganado', cuit='30-6')}
    C = {'1': dict(oportunidadId='a', estado='enviada', neto=100, vence='2026-11-01', familia='Cables de fibra'),
         '2': dict(oportunidadId='b', estado='enviada', neto=900, vence='2026-12-30', familia='ONT'),
         '3': dict(oportunidadId='c', estado='enviada', neto=50, vence='2026-11-10', familia='OLT'),
         '4': dict(oportunidadId='x', estado='enviada', neto=9999, vence='2026-11-01', familia='ONT'),
         '5': dict(oportunidadId='g', estado='enviada', neto=5000, vence='2026-11-01', familia='ONT')}
    f = calcular({'oportunidades': O, 'cotizaciones': C}, {'309'}, set(), [('306', 1), ('304', 2)], {'305'}, hoy, {})
    ids = [x['crm_id'] for x in f]
    f2 = calcular({'oportunidades': O, 'cotizaciones': C}, {'309'}, set(), [('304', 2)], {'305'}, hoy,
                  {'a': {x['pregunta'] for x in f if x['crm_id'] == 'a'}})
    casos = [
        ('2 cotizaciones: primero las vencidas, por monto', ids[:2] == ['a', 'c']),
        ('excluida (otro vendedor) y ganada no entran', 'x' not in ids and 'g' not in ids),
        ('recompra, base FH sin OLT y lead', ids[2:] == ['r', 'f', 'l']),
        ('cada fila con pregunta y dato a cargar', all(x['pregunta'] and x['dato_a_cargar'] for x in f)),
        ('no repite la pregunta de ayer', next(x['pregunta'] for x in f2 if x['crm_id'] == 'a') != next(x['pregunta'] for x in f if x['crm_id'] == 'a')),
    ]
    for t, okk in casos:
        print(('  OK    ' if okk else '  FALLA ') + t)
    k = sum(x for _, x in casos)
    print(f'autotest cola_dia: {k}/{len(casos)}')
    return 0 if k == len(casos) else 1


def loki(ruta):
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def leer(db, hoy):
    q = lambda s, a=(): db.run([(s, list(a))])[0][1]
    crm = {'oportunidades': {}, 'cotizaciones': {}}
    for col, i, data in q("SELECT coleccion, id, data FROM crm WHERE coleccion IN ('oportunidades','cotizaciones')"):
        crm[col][i] = json.loads(data or '{}')
    excl_cuit = {dig(r[0]) for r in q("SELECT cuit FROM cue_cuentas WHERE estado IN (?,?,?) AND cuit IS NOT NULL", EXCL)}
    excl_id = {r[0] for r in q("SELECT crm_id FROM cue_cuentas WHERE estado IN (?,?,?) AND crm_id IS NOT NULL", EXCL)}
    red = q("SELECT cuit, puesto FROM red_pred WHERE politica='red_neuronal' AND corte=(SELECT max(corte) FROM red_pred WHERE politica='red_neuronal') AND puesto IS NOT NULL AND dias_ult >= max(15, coalesce(ciclo, 0) * 0.7) ORDER BY puesto")
    fh = {dig(r[0]) for r in q("SELECT DISTINCT cuit FROM limpia_compras_firmes WHERE marca LIKE '%iber%ome%' AND upper(subfamilia) LIKE 'ONU%' AND coalesce(otro_vendedor,0)=0")}
    ayer = {}
    try:
        for k, p in q('SELECT crm_id, pregunta FROM cola_dia WHERE dia = (SELECT max(dia) FROM cola_dia WHERE dia < ?)', [hoy.isoformat()]):
            ayer.setdefault(k, set()).add(p)
    except RuntimeError:
        pass
    return crm, excl_cuit, excl_id, [(dig(c), p) for c, p in red], fh, ayer


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    if a[:1] in (['correr'], ['simular']):
        hoy = D.date.fromisoformat(a[a.index('--hoy') + 1]) if '--hoy' in a else D.datetime.now(D.timezone(D.timedelta(hours=-3))).date()
        db = loki(os.path.join(AQUI, '..', 'loki', 'loki_sql.py')).conectar()
        d = leer(db, hoy)
        filas = calcular(*d[:5], hoy, d[5])
        if a[0] == 'correr':
            ahora = D.datetime.now(D.timezone.utc).isoformat(timespec='seconds')
            db.run([('CREATE TABLE IF NOT EXISTS cola_dia(' + ', '.join(COLS) + ')', []), ('DELETE FROM cola_dia WHERE dia = ?', [hoy.isoformat()])]
                   + [('INSERT INTO cola_dia VALUES(' + ','.join('?' * len(COLS)) + ')', [f.get(c, ahora) if c != 'calculado' else ahora for c in COLS]) for f in filas])
        db.close()
        for f in filas:
            print(f"{f['puesto']}. [{f['bloque']}] {f['cuenta']} · {f['motivo']}\n     → {f['pregunta']}  (cargar: {f['dato_a_cargar']})")
        print('RESUMEN ' + json.dumps(dict(dia=hoy.isoformat(), filas=len(filas), bloques=[f['bloque'] for f in filas]), ensure_ascii=False))
        sys.exit(0)
    print(__doc__)
