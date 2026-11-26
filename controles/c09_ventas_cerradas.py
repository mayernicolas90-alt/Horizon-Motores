"""C09 · las ventas de un mes cerrado no se mueven. Ventas = CRM (loki/ventas.py: aceptadas por fechaGanada, neto sin
IVA, sin archivadas ni vendedor «otro»), nunca Finnegans. Si un cambio en el CRM o en el cálculo mueve un mes ya cerrado,
FALLA y hay que mirar qué cambió antes de seguir.
Meses fijos: octubre 2026 = USD 73.964,21 sin IVA (la cifra que Nicolás dio por buena; 26/11 se confirmó con Swissnet
0000-00023 y Bertone FA 1699 marcadas vendedor = otro). Un mes nuevo se suma acá solo cuando Nicolás lo da por cerrado."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'loki'))
from ventas import ventas_mes

CERRADOS = {'2026-10': 73964.21}


def chequear(q):
    mal, ok = [], []
    for mes, esperado in CERRADOS.items():
        r = ventas_mes(q, mes)
        (ok if abs(r['neto'] - esperado) < 0.005 else mal).append(f"{mes} {r['neto']:.2f} (esperado {esperado:.2f}, {r['cotizaciones']} cot.)")
    return ('FALLA', 'se movió: ' + ' · '.join(mal)) if mal else ('PASA', ' · '.join(ok))


def _prueba():
    """Sin datos reales: una base en memoria con un mes que suma bien y roturas que tienen que dar otra cifra."""
    import json, sqlite3
    db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE crm (coleccion TEXT, id TEXT, data TEXT)')
    docs = [
        ('a', dict(numero='NM1', cliente='A', estado='aceptada', fechaGanada='2026-10-05', neto=100.0)),
        ('b', dict(numero='NM2', cliente='B', estado='aceptada', fechaGanada='2026-10-20', neto='50.5')),          # neto como texto
        ('c', dict(numero='NM3', cliente='C', estado='aceptada', fechaGanada='2026-10-21', neto=999, vendedor='otro')),
        ('d', dict(numero='NM4', cliente='D', estado='aceptada', fechaGanada='2026-10-22', neto=999, archivada=1)),
        ('e', dict(numero='NM5', cliente='E', estado='enviada', fecha='2026-10-23', neto=999)),
        ('f', dict(numero='NM6', cliente='F', estado='aceptada', fechaGanada='2026-11-01', neto=999)),
        ('g', dict(numero='NM7', cliente='G', estado='aceptada', fechaGanada='2026-10-30T12:00:00Z', neto=10, archivada=0)),
    ]
    for i, d in docs:
        db.execute('INSERT INTO crm VALUES (?,?,?)', ('cotizaciones', i, json.dumps(d)))
    db.execute('INSERT INTO crm VALUES (?,?,?)', ('oportunidades', 'z', json.dumps(dict(estado='aceptada', fechaGanada='2026-10-01', neto=999))))
    q = lambda sql, args=(): [dict(x) for x in db.execute(sql, args)]
    r, vacio = ventas_mes(q, '2026-10'), ventas_mes(q, '2026-09')
    casos = [
        ('suma solo aceptadas del mes, sin otro vendedor ni archivadas', r['neto'] == 160.5 and r['cotizaciones'] == 3),
        ('mes sin ventas: sin_datos', vacio['estado'] == 'sin_datos' and vacio['neto'] == 0),
    ]
    try:
        ventas_mes(q, '2026-13'); casos.append(('mes inválido frena', False))
    except ValueError:
        casos.append(('mes inválido frena', True))
    global CERRADOS
    guardado, CERRADOS = CERRADOS, {'2026-10': 160.5}
    casos.append(('cifra fija igual: PASA', chequear(q)[0] == 'PASA'))
    CERRADOS = {'2026-10': 161.0}
    casos.append(('cifra movida: FALLA', chequear(q)[0] == 'FALLA'))
    CERRADOS = guardado
    mal = [n for n, b in casos if not b]
    return ('FALLA', 'prueba rota: ' + ', '.join(mal)) if mal else ('PASA', f'{len(casos)} casos de prueba')


def correr(modo):
    if modo == 'ci':
        return _prueba()
    from bitacora2 import turso
    return chequear(lambda sql, args=(): turso(sql, args))
