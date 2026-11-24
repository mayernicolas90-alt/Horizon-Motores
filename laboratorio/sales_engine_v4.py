#!/usr/bin/env python3
"""sales_engine_v4.py 0.1 · laboratorio (24/11/2026) · propuesta de Sales Engine que empuja ventas.

Auditoría del Sales Engine actual (página del CRM, R6.4/R6.5 + config/salesEngine 3.0) y de su copia en el datacenter
(portada.py → por_dia):
  1. El nivel 0 («cierre») es cualquier ficha con una cotización abierta, sin importar la antigüedad. Pero en el CRM
     las 28 cotizaciones ganadas se cerraron a los 0 días de mediana, 14 el 90 % y 21 como máximo. Hoy 11 de las 12
     abiertas tienen más de 21 días: el motor pone arriba, todos los días, negocios que en la historia no se ganaron.
  2. El nivel 1 («recompra le toca / atrasado», +14/+8) es la señal que peor encuentra compradores en la prueba hacia
     atrás sobre cuentas elegibles (1,57 de 10 a 30 días; «más reciente» da 2,24 y la red 2,48).
  3. Ordena por monto: el cable grande (35 % de cierre; arriba de USD 20.000 se ganó 1 de 5) tapa a la ONU (75 %).
  4. No tiene memoria: repite las mismas cuentas con la misma acción todos los días.
Propuesta v4 (este script la calcula sobre la copia del CRM en Turso, sin tocar nada):
  · Valor esperado = probabilidad × monto. Probabilidad de la cotización = tasa de cierre de su familia (suavizada)
    × frescura (≤ 14 días 1,0 · 15-21 días 0,5 · > 21 días 0,1).
  · Cupos para los 10 del día: hasta 4 cotizaciones frescas (≤ 21 días) · 3 recompras (red en prueba; si no,
    «más reciente») · 2 decisiones sobre cotizaciones viejas («actualizar el estado: renovar, en espera con fecha o perdida con motivo» (regla de Nicolás: las cotizaciones nunca se pierden solas),
    por valor) · 1 cuenta FiberHome sin la OLT relevada. Si un cupo no se llena, pasa al siguiente.
  · No entran: excluidas (no prospectar, otro vendedor, archivada), fichas archivadas, ganadas en posventa.
  · No repite la misma acción de ayer a la misma cuenta (lee se4_dia del día anterior).
Escribe solo se4_dia (DEC-1124a). Uso: python3 -I laboratorio/sales_engine_v4.py correr|simular [--hoy AAAA-MM-DD] · --autotest
    Recompra: no se llama al que acaba de comprar. Entra recién cuando pasaron 15 días y el 70 % de su ciclo
    (pedido de Nicolás, 24/11: no llamar por recompra a quien acaba de comprar).
"""
import datetime as D, importlib.util, json, os, re, sys

VERSION = 'sales_engine_v4 0.1 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
ABIERTAS, GANADAS, PERDIDAS = {'enviada', 'espera_aprobacion'}, {'aceptada', 'ganada'}, {'rechazada', 'perdida', 'cancelada'}
EXCL = ('no_prospectar', 'otro_vendedor', 'archivada')
CUPOS = [('cotizacion_fresca', 4), ('recompra', 3), ('decidir_cotizacion_vieja', 2), ('base_fh', 1)]
COLS = ['dia', 'puesto', 'bloque', 'crm_id', 'cuenta', 'valor_esperado', 'prob', 'monto', 'motivo', 'accion', 'version', 'calculado']
dig = lambda s: re.sub(r'\D', '', str(s or ''))


def fd(s):
    return D.date.fromisoformat(str(s)[:10]) if str(s or '')[:4].isdigit() else None


def familia(c):
    f = str(c.get('familia') or '').lower()
    return ('onu' if re.search(r'\bont\b|\bonu\b', f) else 'cable' if 'cable' in f or 'fibra' in f
            else 'olt' if 'olt' in f else 'cajas' if 'caja' in f or 'nap' in f else 'otros')


def tasas(cots):
    """Tasa de cierre por familia, suavizada hacia la tasa general (Laplace con peso 2)."""
    g = sum(1 for c in cots if str(c.get('estado')) in GANADAS)
    p = sum(1 for c in cots if str(c.get('estado')) in PERDIDAS)
    gen = (g + 1) / (g + p + 2)
    out = {}
    for f in ('onu', 'cable', 'olt', 'cajas', 'otros'):
        gf = sum(1 for c in cots if familia(c) == f and str(c.get('estado')) in GANADAS)
        pf = sum(1 for c in cots if familia(c) == f and str(c.get('estado')) in PERDIDAS)
        out[f] = round((gf + 2 * gen) / (gf + pf + 2), 3)
    return out


def frescura(dias):
    return 1.0 if dias <= 14 else 0.5 if dias <= 21 else 0.1


def calcular(O, C, excl_cuit, excl_id, red, fh_onu, hoy, ayer):
    ok = lambda k, o: (k not in excl_id and dig(o.get('cuit')) not in excl_cuit and not o.get('archivada')
                       and not o.get('noProspectar') and o.get('etapa') not in ('perdido', 'archivado', 'descartado'))
    T = tasas(list(C.values()))
    cand = {b: [] for b, _ in CUPOS}
    por = {}
    for c in C.values():
        if str(c.get('estado')) in ABIERTAS and not c.get('archivada'):
            por.setdefault(c.get('oportunidadId'), []).append(c)
    for k, cs in por.items():
        o = O.get(k)
        if not o or not ok(k, o):
            continue
        for c in cs:
            dias = (hoy - (fd(c.get('fecha')) or hoy)).days
            monto = float(c.get('neto') or c.get('total') or 0)
            p = T[familia(c)] * frescura(dias)
            num = c.get('numero') or c.get('id')
            base = dict(crm_id=k, cuenta=o.get('empresa') or k, prob=round(p, 3), monto=round(monto, 2), valor_esperado=round(p * monto, 2))
            if dias <= 21:
                cand['cotizacion_fresca'].append(dict(base, bloque='cotizacion_fresca', motivo=f'{num} · {familia(c)} · {dias} días · cierre {T[familia(c)]:.0%}',
                                                      accion='Cerrar: ¿qué falta para la orden de compra?'))
            else:
                cand['decidir_cotizacion_vieja'].append(dict(base, bloque='decidir_cotizacion_vieja',
                                                             motivo=f'{num} · {familia(c)} · {dias} días abierta (ninguna ganada pasó de 21)',
                                                             accion='Actualizar el estado hoy: renovar con precio o condición nueva, en espera con fecha, o perdida con motivo'))
    cuit_op = {}
    for k, o in O.items():
        if dig(o.get('cuit')) and ok(k, o):
            cuit_op.setdefault(dig(o['cuit']), k)
    for cuit, puesto in red:
        k = cuit_op.get(dig(cuit))
        if k and k not in por:
            cand['recompra'].append(dict(crm_id=k, cuenta=O[k].get('empresa') or k, prob=None, monto=None, valor_esperado=-puesto,
                                         bloque='recompra', motivo=f'puesto {puesto} en recompra (red en prueba)',
                                         accion='¿Stock y próxima compra? Cantidad y fecha'))
    for cuit in sorted(fh_onu):
        k = cuit_op.get(dig(cuit))
        if k and not str(O[k].get('marcaOlt') or '').strip():
            cand['base_fh'].append(dict(crm_id=k, cuenta=O[k].get('empresa') or k, prob=None, monto=None, valor_esperado=0,
                                        bloque='base_fh', motivo='compra ONT FiberHome y la ficha no tiene la OLT', accion='¿Qué OLT tienen (marca y modelo)?'))
    pick, usados, sobra = [], set(), 0
    for bloque, cupo in CUPOS:
        n = 0
        for x in sorted(cand[bloque], key=lambda x: -x['valor_esperado']):
            if x['crm_id'] in usados or x['accion'] in ayer.get(x['crm_id'], set()):
                continue
            if n >= cupo + sobra:
                break
            pick.append(x); usados.add(x['crm_id']); n += 1
        sobra = cupo + sobra - n
    for i, x in enumerate(pick, 1):
        x.update(dia=hoy.isoformat(), puesto=i, version=VERSION)
    return pick, T


def autotest():
    hoy = D.date(2026, 11, 24)
    O = {k: dict(empresa=k.upper(), etapa='cotizado', cuit=f'30{i}') for i, k in enumerate(['a', 'b', 'c', 'd', 'x', 'r', 'f'])}
    C = {'h1': dict(oportunidadId='h', estado='aceptada', familia='ONT'), 'h2': dict(oportunidadId='h', estado='aceptada', familia='ONT'),
         'h3': dict(oportunidadId='h', estado='rechazada', familia='Cables de fibra'), 'h4': dict(oportunidadId='h', estado='rechazada', familia='Cables de fibra'),
         '1': dict(oportunidadId='a', estado='enviada', neto=1000, familia='ONT', fecha='2026-11-20'),
         '2': dict(oportunidadId='b', estado='enviada', neto=100000, familia='Cables de fibra', fecha='2026-09-01'),
         '3': dict(oportunidadId='c', estado='enviada', neto=4000, familia='Cables de fibra', fecha='2026-11-15'),
         '4': dict(oportunidadId='x', estado='enviada', neto=9e9, familia='ONT', fecha='2026-11-23')}
    pick, T = calcular(O, C, {'304'}, set(), [('305', 1)], {'306'}, hoy, {})
    by = {x['crm_id']: x for x in pick}
    casos = [
        ('la ONU cierra más que el cable', T['onu'] > T['cable']),
        ('cotización vieja va a «decidir», no a cierre', by['b']['bloque'] == 'decidir_cotizacion_vieja'),
        ('frescas primero, ordenadas por valor esperado', [x['crm_id'] for x in pick][:2] == ['c', 'a']),
        ('excluida no entra', 'x' not in by),
        ('recompra y base FH entran', by['r']['bloque'] == 'recompra' and by['f']['bloque'] == 'base_fh'),
        ('no repite la acción de ayer', 'b' not in {x['crm_id'] for x in calcular(O, C, {'304'}, set(), [], set(), hoy, {'b': {by['b']['accion']}})[0]}),
    ]
    for t, okk in casos:
        print(('  OK    ' if okk else '  FALLA ') + t)
    k = sum(x for _, x in casos)
    print(f'autotest sales_engine_v4: {k}/{len(casos)}')
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
    if a[:1] in (['correr'], ['simular']):
        hoy = D.date.fromisoformat(a[a.index('--hoy') + 1]) if '--hoy' in a else D.datetime.now(D.timezone(D.timedelta(hours=-3))).date()
        db = loki(os.path.join(AQUI, '..', 'loki', 'loki_sql.py')).conectar()
        q = lambda s, p=(): db.run([(s, list(p))])[0][1]
        crm = {'oportunidades': {}, 'cotizaciones': {}}
        for col, i, data in q("SELECT coleccion, id, data FROM crm WHERE coleccion IN ('oportunidades','cotizaciones')"):
            crm[col][i] = json.loads(data or '{}')
        excl_cuit = {dig(r[0]) for r in q('SELECT cuit FROM cue_cuentas WHERE estado IN (?,?,?) AND cuit IS NOT NULL', EXCL)}
        excl_id = {r[0] for r in q('SELECT crm_id FROM cue_cuentas WHERE estado IN (?,?,?) AND crm_id IS NOT NULL', EXCL)}
        red = [(dig(c), p) for c, p in q("SELECT cuit, puesto FROM red_pred WHERE politica='red_neuronal' AND puesto IS NOT NULL AND corte=(SELECT max(corte) FROM red_pred WHERE politica='red_neuronal') AND dias_ult >= max(15, coalesce(ciclo, 0) * 0.7) ORDER BY puesto")]
        fh = {dig(r[0]) for r in q("SELECT DISTINCT cuit FROM limpia_compras_firmes WHERE marca LIKE '%iber%ome%' AND upper(subfamilia) LIKE 'ONU%' AND coalesce(otro_vendedor,0)=0")}
        ayer = {}
        try:
            for k, ac in q('SELECT crm_id, accion FROM se4_dia WHERE dia = (SELECT max(dia) FROM se4_dia WHERE dia < ?)', [hoy.isoformat()]):
                ayer.setdefault(k, set()).add(ac)
        except RuntimeError:
            pass
        pick, T = calcular(crm['oportunidades'], crm['cotizaciones'], excl_cuit, excl_id, red, fh, hoy, ayer)
        if a[0] == 'correr':
            ahora = D.datetime.now(D.timezone.utc).isoformat(timespec='seconds')
            db.run([('CREATE TABLE IF NOT EXISTS se4_dia(' + ', '.join(COLS) + ')', []), ('DELETE FROM se4_dia WHERE dia = ?', [hoy.isoformat()])]
                   + [('INSERT INTO se4_dia VALUES(' + ','.join('?' * len(COLS)) + ')', [x.get(c) if c != 'calculado' else ahora for c in COLS]) for x in pick])
        db.close()
        print('tasas de cierre por familia:', T)
        for x in pick:
            ve = f" · valor esperado USD {x['valor_esperado']:,.0f}" if x['monto'] else ''
            print(f"{x['puesto']:2d}. [{x['bloque']}] {x['cuenta']} · {x['motivo']}{ve}\n      → {x['accion']}")
        sys.exit(0)
    print(__doc__)
