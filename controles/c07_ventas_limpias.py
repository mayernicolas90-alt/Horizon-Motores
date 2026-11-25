"""C07 · alerta diaria: `ventas` (renglones del R10 que verifica el auditor) es la fuente y las tablas limpia_* se
derivan de ella. Las dos tienen que coincidir renglón por renglón (limpia_renglones.id = ventas.n): mismo
comprobante, CUIT (solo dígitos), producto y cantidad, y ningún renglón de un lado sin el otro.
Paso 2 del datacenter (24/11): `ventas` no pasa a vista porque las limpias no tienen importe, pte_dest, precio,
documento ni cod_producto, que usan loki_sql, enlace, bitacora2 y el auditor. Este control cierra el «FALTA control»."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'loki'))

DIGITOS = "replace(replace(replace(replace(COALESCE({c},''),'-',''),'.',''),' ',''),'/','')"
CONSULTA = f"""SELECT
 (SELECT COUNT(*) FROM ventas) AS ventas,
 (SELECT COUNT(*) FROM limpia_renglones) AS limpias,
 (SELECT COUNT(*) FROM ventas v LEFT JOIN limpia_renglones r ON r.id = v.n WHERE r.id IS NULL) AS sin_limpia,
 (SELECT COUNT(*) FROM limpia_renglones r LEFT JOIN ventas v ON v.n = r.id WHERE v.n IS NULL) AS sin_venta,
 (SELECT COUNT(*) FROM limpia_renglones r LEFT JOIN limpia_comprobantes c ON c.tid = r.tid WHERE c.tid IS NULL) AS sin_comprobante,
 (SELECT COUNT(*) FROM limpia_renglones r JOIN limpia_comprobantes c ON c.tid = r.tid JOIN ventas v ON v.n = r.id
   WHERE COALESCE(c.comprobante,'') <> COALESCE(v.comprobante,'')
      OR {DIGITOS.format(c='c.cuit')} <> {DIGITOS.format(c='v.cuit')}
      OR COALESCE(r.producto,'') <> COALESCE(v.producto,'')
      OR ABS(COALESCE(r.cantidad,0) - COALESCE(v.cantidad,0)) > 0.0001) AS distintos"""


def chequear(q):
    r = {k: int(v or 0) for k, v in q(CONSULTA)[0].items()}   # Turso devuelve los enteros como texto ('0' es verdadero)
    det = (f"ventas {r['ventas']} · limpias {r['limpias']} · sin limpia {r['sin_limpia']} · sin venta {r['sin_venta']}"
           f" · sin comprobante {r['sin_comprobante']} · distintos {r['distintos']}")
    ok = r['ventas'] == r['limpias'] and not (r['sin_limpia'] or r['sin_venta'] or r['sin_comprobante'] or r['distintos'])
    return ('PASA' if ok else 'FALLA'), det


def _prueba():
    """Sin datos reales: una base en memoria que coincide (PASA) y tres roturas que tienen que dar FALLA."""
    import sqlite3

    def base(extra=()):
        db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE ventas (n INTEGER PRIMARY KEY, comprobante TEXT, cuit TEXT, producto TEXT, cantidad REAL);
            CREATE TABLE limpia_comprobantes (tid TEXT, comprobante TEXT, cuit TEXT);
            CREATE TABLE limpia_renglones (id INTEGER, tid TEXT, producto TEXT, cantidad REAL);
            INSERT INTO ventas VALUES (1,'A-1','30-71554899-9','ONT',10),(2,'B-2','16.497.924','Drop',5);
            INSERT INTO limpia_comprobantes VALUES ('t1','A-1','30715548999'),('t2','B-2','16497924');
            INSERT INTO limpia_renglones VALUES (1,'t1','ONT',10),(2,'t2','Drop',5);""")
        for s in extra:
            db.execute(s)
        return lambda sql: [dict(x) for x in db.execute(sql)]

    casos = [
        ('coinciden', (), 'PASA'),
        ('renglón de ventas sin limpia', ("INSERT INTO ventas VALUES (3,'A-3','30715548999','ONT',1)",), 'FALLA'),
        ('cantidad distinta', ("UPDATE limpia_renglones SET cantidad=9 WHERE id=1",), 'FALLA'),
        ('CUIT distinto', ("UPDATE limpia_comprobantes SET cuit='20111111112' WHERE tid='t2'",), 'FALLA'),
    ]
    mal = [n for n, extra, esperado in casos if chequear(base(extra))[0] != esperado]
    como_turso = lambda q: (lambda sql: [{k: str(v) for k, v in x.items()} for x in q(sql)])   # enteros como texto
    if chequear(como_turso(base()))[0] != 'PASA':
        mal.append('enteros como texto (Turso)')
    casos.append(('enteros como texto', (), 'PASA'))
    return ('FALLA', 'prueba rota: ' + ', '.join(mal)) if mal else ('PASA', f'{len(casos)} casos de prueba')


def correr(modo):
    if modo == 'ci':
        return _prueba()
    from bitacora2 import turso
    return chequear(turso)
