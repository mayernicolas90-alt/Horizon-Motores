#!/usr/bin/env python3
"""red_auditor.py 0.1 · laboratorio (24/11/2026) · mide las predicciones guardadas en red_pred contra lo que pasó.

Para cada corte de red_pred cuya ventana ya está completa (corte + N días ≤ último dato de limpia_compras_firmes),
y para cada política (red, regla de ciclo, más reciente, las de la sesión Loki…), calcula:
  aciertos_top10 · compradores entre los 10 primeros (sin excluidas por cue_cuentas)
  compradores    · cuántos clientes elegibles compraron en la ventana (el techo)
  cobertura      · aciertos_top10 / compradores
Escribe solo red_eval (DEC-1124a). Veredicto por política contra el piso (el mejor entre regla_ciclo y ref_reciente en cada corte): GANA si en las últimas 4
ventanas completas promedia +1 comprador cada 10 o más, EMPATA si está entre 0 y +1, PIERDE si queda abajo.
Uso: python3 -I laboratorio/red_auditor.py correr · --autotest
"""
import datetime as D, importlib.util, json, os, sys

VERSION = 'red_auditor 0.2 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
PISOS, META, VENTANAS = ('regla_ciclo', 'ref_reciente'), 1.0, 4  # el piso es el mejor de los dos en cada corte
COLS = ['corte', 'politica', 'horizonte', 'aciertos_top10', 'compradores', 'cobertura', 'elegibles', 'version', 'calculado']


def evaluar(pred, compras, ultimo, horizonte):
    """pred: [(corte, cuit, politica, puesto)] (puesto None = excluida) · compras: {cuit: [fechas]}."""
    por = {}
    for corte, cuit, pol, puesto in pred:
        por.setdefault((corte, pol), []).append((puesto, cuit))
    out = []
    for (corte, pol), xs in sorted(por.items()):
        c = D.date.fromisoformat(corte)
        if c + D.timedelta(days=horizonte) > ultimo:
            continue
        compro = lambda cuit: any(c < f <= c + D.timedelta(days=horizonte) for f in compras.get(cuit, []))
        eleg = [(p, cu) for p, cu in xs if p is not None]
        top = [cu for p, cu in sorted(eleg)[:10]]
        ac, comp = sum(map(compro, top)), sum(compro(cu) for _, cu in eleg)
        out.append(dict(corte=corte, politica=pol, horizonte=horizonte, aciertos_top10=ac, compradores=comp,
                        cobertura=round(ac / comp, 3) if comp else None, elegibles=len(eleg)))
    return out


def veredicto(evals, horizonte):
    filas = [e for e in evals if e['horizonte'] == horizonte]
    cortes = sorted({e['corte'] for e in filas if e['politica'] in PISOS})[-VENTANAS:]
    if len(cortes) < VENTANAS:
        return {'estado': 'SIN_DATOS', 'detalle': f'{len(cortes)} de {VENTANAS} ventanas completas a {horizonte} días'}
    piso = {}
    for e in filas:
        if e['politica'] in PISOS and e['corte'] in cortes:
            piso[e['corte']] = max(piso.get(e['corte'], 0), e['aciertos_top10'])
    res = {}
    for pol in sorted({e['politica'] for e in filas} - set(PISOS)):
        v = [e['aciertos_top10'] - piso[e['corte']] for e in filas if e['politica'] == pol and e['corte'] in piso]
        if len(v) < VENTANAS:
            continue
        m = sum(v) / len(v)
        res[pol] = dict(ventaja=round(m, 2), estado='GANA' if m >= META else 'EMPATA' if m >= 0 else 'PIERDE')
    return res


def autotest():
    d = D.date.fromisoformat
    compras = {'A': [d('2026-01-10')], 'B': [d('2026-01-20')], 'C': [d('2026-03-01')]}
    pred = [('2026-01-01', 'A', 'red', 1), ('2026-01-01', 'B', 'red', 2), ('2026-01-01', 'C', 'red', 3),
            ('2026-01-01', 'C', 'regla_ciclo', 1), ('2026-01-01', 'A', 'regla_ciclo', None), ('2026-01-01', 'B', 'regla_ciclo', 2),
            ('2026-11-10', 'A', 'red', 1)]
    ev = evaluar(pred, compras, d('2026-11-20'), 30)
    red = next(e for e in ev if e['politica'] == 'red')
    reg = next(e for e in ev if e['politica'] == 'regla_ciclo')
    casos = [
        ('cuenta compradores del top 10 dentro de la ventana', red['aciertos_top10'] == 2 and red['compradores'] == 2),
        ('las excluidas no cuentan ni en el top ni en el techo', reg['aciertos_top10'] == 1 and reg['elegibles'] == 2),
        ('ventana incompleta no se evalúa', not any(e['corte'] == '2026-11-10' for e in ev)),
        ('sin 4 ventanas: SIN_DATOS', veredicto(ev, 30).get('estado') == 'SIN_DATOS'),
    ]
    ev4 = [dict(corte=f'2026-0{i}-01', politica=p, horizonte=30, aciertos_top10=a) for i in range(1, 5) for p, a in (('regla_ciclo', 4), ('red', 6))]
    casos.append(('+2 cada 10 en 4 ventanas: GANA', veredicto(ev4, 30)['red']['estado'] == 'GANA'))
    ev5 = ev4 + [dict(corte=f'2026-0{i}-01', politica='ref_reciente', horizonte=30, aciertos_top10=6) for i in range(1, 5)]
    casos.append(('el piso es el mejor de los dos: empata con «más reciente»', veredicto(ev5, 30)['red']['estado'] == 'EMPATA'))
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    ok = sum(x for _, x in casos)
    print(f'autotest red_auditor: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


def loki(ruta):
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    if a[:1] == ['correr']:
        db = loki(os.path.join(AQUI, '..', 'loki', 'loki_sql.py')).conectar()
        q = lambda s: db.run([(s, [])])[0][1]
        compras = {}
        for cuit, f in q('SELECT cuit, fecha FROM limpia_compras_firmes WHERE coalesce(otro_vendedor,0)=0 AND cantidad_neta > 0'):
            compras.setdefault(cuit, []).append(D.date.fromisoformat(f[:10]))
        ultimo = max(f for fs in compras.values() for f in fs)
        pred = [tuple(r) for r in q('SELECT corte, cuit, politica, puesto FROM red_pred')]
        ev = evaluar(pred, compras, ultimo, 30) + evaluar(pred, compras, ultimo, 60)
        ahora = D.datetime.now(D.timezone.utc).isoformat(timespec='seconds')
        db.run([('CREATE TABLE IF NOT EXISTS red_eval(' + ', '.join(COLS) + ')', []), ('DELETE FROM red_eval', [])]
               + [('INSERT INTO red_eval VALUES(' + ','.join('?' * len(COLS)) + ')',
                   [e['corte'], e['politica'], e['horizonte'], e['aciertos_top10'], e['compradores'], e['cobertura'], e['elegibles'], VERSION, ahora]) for e in ev])
        db.close()
        print('RESUMEN ' + json.dumps(dict(ultimo_dato=ultimo.isoformat(), cortes_pred=len({p[0] for p in pred}), evaluadas=len(ev),
                                           veredicto_30=veredicto(ev, 30), veredicto_60=veredicto(ev, 60)), ensure_ascii=False))
        sys.exit(0)
    print(__doc__)
