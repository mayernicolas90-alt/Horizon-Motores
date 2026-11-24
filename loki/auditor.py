#!/usr/bin/env python3
"""auditor.py 0.1 · Auditor del datacenter de Loki (24/11/2026, DEC-1124a/c).

Revisa lo que entra y lo que sale de cada motor, con código propio (no importa ningún motor).
Solo escribe en su tabla aud_resultados: nunca modifica datos.

Veredicto de una corrida: FALLA si algún control da FALLA (el publicador no publica) · AVISO si hay algo para mirar ·
PASA si está todo bien. La última línea de la salida es «AUDITOR <veredicto> · ...» (la lee dc.py).

Controles generales (toda corrida): G1 el motor terminó bien · G2 no escribió fuera de su contrato.
Controles de Limpieza:
  L1 cada comprobante una sola vez (TransaccionID) · L2 entrada = salida: todo comprobante de Horizon del R10 desde 2024 está limpio
  L3 cada NC vinculada a su factura o en «a revisar» · L4 cantidad neta entre 0 y lo facturado · L5 hay compras firmes
  L6 sin precios ni importes en los renglones · L7 datos con menos de 10 días · L8 NC a revisar de cuentas propias
  L9 comprobantes de cuentas propias sin renglones

Uso (python3 -I): auditor.py correr --corrida N [--loki ruta] · auditor.py --contrato · auditor.py --autotest
"""
import csv, datetime as D, importlib.util, io, json, os, sys

VERSION = 'auditor 0.1 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
EMPRESA = 'HORIZON TRADING S.A.'
CONTRATO = {'id': 'auditor', 'nombre': 'Auditor', 'disparo': 'cada corrida', 'lee': ['*'], 'escribe': ['aud_resultados'],
            'que_hace': 'Controla entradas, salidas y coherencia de cada motor. Nunca modifica datos.'}
DDL = ('CREATE TABLE IF NOT EXISTS aud_resultados(corrida INTEGER, motor TEXT, control TEXT, estado TEXT, detalle TEXT, fecha TEXT)')


def loki(ruta=None):
    ruta = ruta or os.path.join(AQUI, 'loki_sql.py')
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def q(db, sql, args=()):
    cols, filas = db.run([(sql, list(args))])[0]
    return [dict(zip(cols, f)) for f in filas]


def uno(db, sql, args=()):
    return db.run([(sql, list(args))])[0][1][0][0]


def hoy():
    return D.date.today().isoformat()


def controles_limpieza(db, R):
    R('L1', 'cada comprobante una sola vez', *(lambda n, d: ('PASA' if n == d else 'FALLA', f'{n} filas · {d} TransaccionID distintos'))(
        uno(db, 'SELECT count(*) FROM limpia_comprobantes'), uno(db, 'SELECT count(DISTINCT tid) FROM limpia_comprobantes')))
    # L2: entrada = salida, leyendo el crudo con código propio
    f = q(db, "SELECT texto FROM archivos WHERE nombre='R10.csv'")
    if not f:
        R('L2', 'entrada = salida (R10 → limpia)', 'AVISO', 'no está R10.csv en archivos: no se pudo comparar')
    else:
        filas = list(csv.DictReader(io.StringIO(f[0]['texto']), delimiter=';'))
        fecha = lambda r: (r.get('Fecha comprobante') or r.get('Fecha Comprobante') or r.get('Fecha') or '')[:10]
        dc_ = lambda r: 'dif. cambio' in (r.get('Documento') or '').lower()
        entrada = {r['TransaccionID'] for r in filas if (r.get('Empresa') or EMPRESA) == EMPRESA and fecha(r) >= '2024-01-01' and r.get('TransaccionID')}
        salida = {r['tid'] for r in q(db, 'SELECT tid FROM limpia_comprobantes')}
        falta = sorted(entrada - salida)
        R('L2', 'entrada = salida (R10 → limpia)', 'PASA' if not falta else 'FALLA',
          f'{len(entrada)} comprobantes de Horizon en R10 · {len(falta)} sin limpiar' + (f' (ej. {", ".join(falta[:5])})' if falta else ''))
    sueltas = uno(db, "SELECT count(*) FROM limpia_comprobantes c WHERE c.tipo='NC' AND c.tid NOT IN (SELECT nc_tid FROM limpia_vinculos_nc) "
                      "AND c.tid NOT IN (SELECT coalesce(tid,'') FROM limpia_revisar)")
    R('L3', 'cada NC vinculada a su factura o en «a revisar»', 'PASA' if not sueltas else 'FALLA', f'{sueltas} NC sueltas')
    malas = uno(db, "SELECT count(*) FROM limpia_renglones r JOIN limpia_comprobantes c ON c.tid=r.tid WHERE c.tipo='FA' "
                    "AND (r.cantidad_neta < -0.0001 OR r.cantidad_neta > abs(r.cantidad) + 0.0001)")
    R('L4', 'cantidad neta entre 0 y lo facturado', 'PASA' if not malas else 'FALLA', f'{malas} renglones fuera de rango')
    n = uno(db, 'SELECT count(*) FROM limpia_compras_firmes')
    R('L5', 'hay compras firmes', 'PASA' if n else 'FALLA', f'{n} renglones de compra firmes')
    cols = [r['name'].lower() for r in q(db, 'PRAGMA table_info(limpia_renglones)')]
    pre = [c for c in cols if c in ('precio', 'importe', 'bruto', 'total', 'neto')]
    R('L6', 'sin precios ni importes en los renglones', 'PASA' if not pre else 'FALLA', 'columnas: ' + (', '.join(pre) if pre else 'solo cantidades'))
    corte = uno(db, 'SELECT max(fecha) FROM limpia_comprobantes')
    dias = (D.date.fromisoformat(hoy()) - D.date.fromisoformat(corte)).days if corte else None
    R('L7', 'datos con menos de 10 días', 'PASA' if dias is not None and dias <= 10 else 'AVISO',
      f'último comprobante {corte} ({dias} días)' + (' · conviene subir reportes nuevos' if dias and dias > 10 else ''))
    rv = q(db, "SELECT fecha, cliente FROM limpia_revisar WHERE otro_vendedor=0 AND motivo LIKE 'NC%' AND fecha >= '2025-01-01' ORDER BY fecha")
    R('L8', 'NC a revisar de cuentas propias (desde 2025)', 'AVISO' if rv else 'PASA', '; '.join(f"{r['cliente'][:28]} {r['fecha']}" for r in rv) or 'ninguna')
    fr = q(db, "SELECT fecha, cliente FROM limpia_faltan_renglones WHERE otro_vendedor=0 AND fecha >= '2025-01-01' ORDER BY fecha")
    R('L9', 'comprobantes de cuentas propias sin renglones (desde 2025)', 'AVISO' if fr else 'PASA', '; '.join(f"{r['cliente'][:28]} {r['fecha']}" for r in fr) or 'ninguno')


CONTROLES = {'limpieza': controles_limpieza}


def correr(corrida, loki_ruta=None):
    L = loki(loki_ruta)
    db = L.conectar()
    db.run([(DDL, [])])
    c = q(db, 'SELECT * FROM dc_corridas WHERE id=?', [corrida])
    if not c:
        print(f'AUDITOR FALLA · no existe la corrida {corrida}')
        return 1
    c = c[0]
    res = []
    def R(ctrl, texto, estado, detalle=''):
        res.append((ctrl, texto, estado, detalle))
    R('G1', 'el motor terminó bien', 'PASA' if c['estado'] == 'OK' else 'FALLA', c['estado'])
    fuera = json.loads(c['fuera_contrato'] or '[]')
    R('G2', 'no escribió fuera de su contrato', 'PASA' if not fuera else 'FALLA', ', '.join(fuera) or 'solo sus tablas')
    if c['estado'] == 'OK' and c['motor'] in CONTROLES:
        try:
            CONTROLES[c['motor']](db, R)
        except Exception as e:  # noqa: BLE001
            R('X', 'los controles corrieron', 'FALLA', f'{type(e).__name__}: {str(e)[:200]}')
    f = D.datetime.now(D.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    db.run([('INSERT INTO aud_resultados VALUES(?,?,?,?,?,?)', [corrida, c['motor'], k + ' ' + t, e, d, f]) for k, t, e, d in res])
    db.close()
    ver = 'FALLA' if any(r[2] == 'FALLA' for r in res) else 'AVISO' if any(r[2] == 'AVISO' for r in res) else 'PASA'
    for k, t, e, d in res:
        print(f'  {e:5} {k:3} {t} · {d}')
    print(f"AUDITOR {ver} · corrida {corrida} ({c['motor']}) · {len(res)} controles · "
          f"{sum(r[2] == 'FALLA' for r in res)} fallas · {sum(r[2] == 'AVISO' for r in res)} avisos")
    return 0


def autotest():
    import sqlite3, tempfile, shutil, subprocess
    d = tempfile.mkdtemp()
    shutil.copy(os.path.join(AQUI, 'loki_sql.py'), d)
    base = os.path.join(d, 'b.sqlite')
    c = sqlite3.connect(base)
    r10 = 'TransaccionID;Fecha;Empresa;Documento\n1;2026-11-20;HORIZON TRADING S.A.;Factura\n2;2026-11-21;HORIZON TRADING S.A.;Nota de Crédito\n3;2026-11-21;SUR TECHNOLOGY S.A.;Factura\n'
    c.executescript(f"""
     CREATE TABLE archivos(nombre, sha256, bytes, texto); INSERT INTO archivos VALUES('R10.csv','h',1,'{r10}');
     CREATE TABLE dc_corridas(id INTEGER PRIMARY KEY, motor, disparo, inicio, fin, estado, huella_entrada, resumen, fuera_contrato, auditor);
     INSERT INTO dc_corridas VALUES(1,'limpieza','finnegans','','','OK','','','[]',NULL);
     INSERT INTO dc_corridas VALUES(2,'limpieza','finnegans','','','OK','','','["ventas"]',NULL);
     CREATE TABLE limpia_comprobantes(tid, fecha, tipo, cliente); INSERT INTO limpia_comprobantes VALUES('1','{hoy()}','FA','X'),('2','{hoy()}','NC','X');
     CREATE TABLE limpia_renglones(tid, producto, clase, cantidad, cantidad_neta);
     INSERT INTO limpia_renglones VALUES('1','Ont','producto',10,6),('2','Ont','producto',-4,0);
     CREATE TABLE limpia_vinculos_nc(nc_tid, factura_tid, metodo, alcance); INSERT INTO limpia_vinculos_nc VALUES('2','1','referencia','parcial');
     CREATE TABLE limpia_revisar(tid, fecha, cliente, motivo, detalle, otro_vendedor);
     CREATE TABLE limpia_faltan_renglones(tid, fecha, documento, comprobante, cliente, otro_vendedor);
     CREATE VIEW limpia_compras_firmes AS SELECT * FROM limpia_renglones WHERE cantidad_neta>0;
    """)
    c.commit(); c.close()
    env = dict(os.environ, LOKI_SQL_LOCAL=base)
    run = lambda n: subprocess.run([sys.executable, '-X', 'utf8', os.path.join(AQUI, 'auditor.py'), 'correr', '--corrida', str(n), '--loki', os.path.join(d, 'loki_sql.py')],
                                   capture_output=True, text=True, env=env)
    a1 = run(1)
    a2 = run(2)
    c = sqlite3.connect(base)
    c.execute("DELETE FROM limpia_comprobantes WHERE tid='2'"); c.execute("INSERT INTO limpia_comprobantes VALUES('9','2026-01-01','NC','Y')"); c.commit()
    a3 = run(1)
    escritas = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    c.close()
    casos = [
        ('datos sanos: PASA', 'AUDITOR PASA' in a1.stdout),
        ('escribir fuera de contrato: FALLA', 'AUDITOR FALLA' in a2.stdout and 'ventas' in a2.stdout),
        ('falta un comprobante del R10: FALLA en L2', 'FALLA L2' in a3.stdout),
        ('NC suelta: FALLA en L3', 'FALLA L3' in a3.stdout),
        ('el auditor solo agrega su tabla', set(escritas) - {'archivos', 'dc_corridas', 'limpia_comprobantes', 'limpia_renglones', 'limpia_vinculos_nc',
                                                              'limpia_revisar', 'limpia_faltan_renglones'} == {'aud_resultados'}),
    ]
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    ok = sum(1 for _, x in casos if x)
    print(f'autotest auditor: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    if '--contrato' in a:
        print(json.dumps(dict(CONTRATO, version=VERSION), ensure_ascii=False))
        sys.exit(0)
    if a[:1] == ['correr'] and '--corrida' in a:
        sys.exit(correr(int(a[a.index('--corrida') + 1]), a[a.index('--loki') + 1] if '--loki' in a else None))
    print(__doc__)
