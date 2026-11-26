#!/usr/bin/env python3
"""ventas.py 1.0 · ventas de Nicolás de un mes, desde el CRM (el tablero vivo), nunca desde Finnegans.

Regla (PR23, P21, D15): venta = cotización del CRM 5SPm en estado «aceptada», contada por fechaGanada, neto sin IVA,
sin archivadas y sin las marcadas vendedor = "otro". Lee la copia del CRM en la base de Loki (tabla crm, la copia cruda
que el arranque baja del día; no las tablas derivadas).

Uso (PC):  python -I -X utf8 %USERPROFILE%\\.loki\\conauth.py ventas.py AAAA-MM
Sale un JSON corto: {mes, neto, cotizaciones, detalle[numero, cliente, fechaGanada, neto], fuente, consultado}.
Sin cotizaciones en el mes: neto 0 y estado "sin_datos" (no es un error). Mes mal escrito: sale con error y código 2.
"""
import json, os, re, sys, datetime as dt

VERSION = '1.0'
CONSULTA = """SELECT id,
  json_extract(data,'$.numero') AS numero, json_extract(data,'$.cliente') AS cliente,
  json_extract(data,'$.fechaGanada') AS fecha_ganada, CAST(json_extract(data,'$.neto') AS REAL) AS neto
 FROM crm
 WHERE coleccion = 'cotizaciones'
   AND json_extract(data,'$.estado') = 'aceptada'
   AND substr(json_extract(data,'$.fechaGanada'), 1, 7) = ?
   AND COALESCE(json_extract(data,'$.archivada'), 0) = 0
   AND COALESCE(json_extract(data,'$.vendedor'), '') <> 'otro'
 ORDER BY fecha_ganada, numero"""


def ventas_mes(q, mes):
    """q(sql, args) -> filas como dict. Devuelve el resumen del mes (montos redondeados a 2 decimales)."""
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', mes or ''):
        raise ValueError(f'mes inválido: {mes!r} (se espera AAAA-MM)')
    filas = q(CONSULTA, [mes])
    det = [dict(numero=f['numero'], cliente=f['cliente'], fechaGanada=f['fecha_ganada'], neto=round(float(f['neto'] or 0), 2))
           for f in filas]
    return dict(mes=mes, estado='ok' if det else 'sin_datos', neto=round(sum(d['neto'] for d in det), 2),
                cotizaciones=len(det), detalle=det, fuente='CRM 5SPm (copia cruda, tabla crm de la base de Loki)',
                consultado=dt.datetime.now().isoformat(timespec='seconds'))


def main(a):
    if len(a) != 1:
        print(__doc__); return 2
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from bitacora2 import turso
    try:
        r = ventas_mes(lambda sql, args: turso(sql, args), a[0])
    except ValueError as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False)); return 2
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
