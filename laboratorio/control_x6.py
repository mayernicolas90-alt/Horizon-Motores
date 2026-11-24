#!/usr/bin/env python3
"""control_x6.py 0.1 · control X6: las dos limpiezas de Finnegans tienen que dar la misma venta (acuerdo PM-i/PM-j, 24/11).

Compara, por CUIT y mes, las unidades facturadas de Horizon Trading (solo facturas de producto, sin NC):
  · Loki:  limpia_renglones de facturas, clase producto, antes de aplicar NC (R10 → importar.py), Turso horizon-nicom90
  · PM:    fin_linea con documento FACT*/FCEVTA* y cantidad > 0 (R4 → importar_finnegans.py), Turso horizon-msyer (solo lectura)
Período: desde 2024-01 hasta el último mes completo que tienen las dos.
No copia filas del PM: pide agregados por SQL. No escribe nada.
Uso: python3 -I laboratorio/control_x6.py [--detalle N]
"""
import datetime as D, importlib.util, json, os, re, sys, urllib.request
from collections import defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
PM = 'https://horizon-msyer.aws-sa-east-1.turso.io/v2/pipeline'
dig = lambda s: re.sub(r'\D', '', str(s or ''))


def pm(sql):
    body = json.dumps({'requests': [{'type': 'execute', 'stmt': {'sql': sql}}, {'type': 'close'}]}).encode()
    rq = urllib.request.Request(PM, data=body, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer proxy-injected'})
    r = json.load(urllib.request.urlopen(rq, timeout=120))['results'][0]
    if r['type'] != 'ok':
        raise RuntimeError(r)
    return [[v.get('value') for v in row] for row in r['response']['result']['rows']]


def main(a):
    n = int(a[a.index('--detalle') + 1]) if '--detalle' in a else 10
    sp = importlib.util.spec_from_file_location('l', os.path.join(AQUI, '..', 'loki', 'loki_sql.py'))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    db = m.conectar()
    hasta_loki = db.run([('SELECT max(fecha) FROM limpia_compras_firmes', [])])[0][1][0][0]
    hasta_pm = pm("SELECT max(fecha) FROM fin_linea WHERE empresa='HORIZON TRADING S.A.'")[0][0]
    fin = min(hasta_loki, hasta_pm)[:7]
    ultimo_mes = (D.date.fromisoformat(fin + '-01') - D.timedelta(days=1)).isoformat()[:7]  # último mes completo
    L = defaultdict(float)
    # facturado bruto de Loki (antes de aplicar NC), para comparar lo mismo que el PM
    for cuit, mes, q in db.run([("SELECT c.cuit, substr(c.fecha,1,7), sum(r.cantidad) FROM limpia_renglones r JOIN limpia_comprobantes c "
                                 "ON c.tid = r.tid WHERE c.tipo = 'FA' AND r.clase = 'producto' AND r.cantidad > 0 AND c.fecha >= '2024-01-01' "
                                 "GROUP BY 1,2", [])])[0][1]:
        if mes <= ultimo_mes:
            L[(dig(cuit), mes)] += float(q or 0)
    db.close()
    P = defaultdict(float)
    for cuit, mes, q in pm("SELECT cuit, substr(fecha,1,7), sum(cantidad) FROM fin_linea WHERE empresa='HORIZON TRADING S.A.' "
                           "AND fecha >= '2024-01-01' AND cantidad > 0 AND (doc LIKE 'FACT%' OR doc LIKE 'FCEVTA%') GROUP BY 1,2"):
        if mes <= ultimo_mes:
            P[(dig(cuit), mes)] += float(q or 0)
    claves = set(L) | set(P)
    igual = sum(1 for k in claves if abs(L.get(k, 0) - P.get(k, 0)) < 0.5)
    solo_l = [k for k in claves if k not in P]; solo_p = [k for k in claves if k not in L]
    dif = sorted(((abs(L.get(k, 0) - P.get(k, 0)), k) for k in claves if k in L and k in P and abs(L[k] - P[k]) >= 0.5), reverse=True)
    print(f'X6 · unidades facturadas por CUIT y mes · 2024-01 a {ultimo_mes} (Loki hasta {hasta_loki}, PM hasta {hasta_pm})')
    print(f'  combinaciones CUIT-mes: {len(claves)} · iguales: {igual} ({igual / max(len(claves), 1):.0%})')
    print(f'  solo en Loki: {len(solo_l)} · solo en PM: {len(solo_p)} · en los dos con distinta cantidad: {len(dif)}')
    print(f'  unidades totales: Loki {sum(L.values()):,.0f} · PM {sum(P.values()):,.0f}')
    for d, (c, mes) in dif[:n]:
        print(f'    {c} {mes}: Loki {L[(c, mes)]:,.0f} · PM {P[(c, mes)]:,.0f}')
    for nombre, xs, src in (('solo Loki', solo_l, L), ('solo PM', solo_p, P)):
        if xs:
            print(f'  {nombre} (mayores): ' + ', '.join(f'{c} {mes} ({src[(c, mes)]:,.0f})' for c, mes in sorted(xs, key=lambda k: -src[k])[:n]))
    print('RESUMEN X6 ' + ('PASA' if igual == len(claves) else 'DIFERENCIAS'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
