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
import csv, datetime as D, importlib.util, io, json, os, re, sys

VERSION = 'auditor 0.3 · 2026-11-24'
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


ESTADOS_REC = {'Le toca', 'Atrasado', 'Se fue', 'Reemplazo (ONU Huawei → FH)', 'Sin ciclo (1 compra)', 'En ciclo', 'Reemplazo (discontinuado)',
               'Sin marca (revisar)', 'Otra marca', 'Ya migró a FH', 'Switch (campaña, fuera del motor)', 'Dormido'}
URG = ['Le toca', 'Atrasado', 'Se fue', 'Reemplazo (ONU Huawei → FH)', 'Sin ciclo (1 compra)', 'En ciclo']


def controles_recompra(db, R):
    n, d = uno(db, 'SELECT count(*) FROM rec_sku'), uno(db, "SELECT count(*) FROM (SELECT DISTINCT cuit, sku FROM rec_sku)")
    R('R1', 'una fila por cliente y SKU', 'PASA' if n == d and n else 'FALLA', f'{n} filas · {d} combinaciones')
    falta = uno(db, "SELECT count(DISTINCT c.cuit) FROM limpia_renglones r JOIN limpia_comprobantes c ON c.tid=r.tid WHERE c.tipo='FA' AND r.clase='producto' "
                    "AND r.cantidad_neta > 0.0001 AND c.cuit <> '' AND c.cuit NOT IN (SELECT cuit FROM rec_cliente)")
    R('R2', 'todo cliente con compras firmes tiene recompra', 'PASA' if not falta else 'FALLA', f'{falta} clientes sin calcular')
    mal = [r for r in q(db, 'SELECT cuit, sku, ultima, ciclo_dias, proxima, compras FROM rec_sku')
           if (r['ciclo_dias'] is not None and (r['compras'] < 2 or r['ciclo_dias'] <= 0 or
               r['proxima'] != (D.date.fromisoformat(r['ultima']) + D.timedelta(days=int(r['ciclo_dias']))).isoformat()))
           or (r['ciclo_dias'] is None and r['compras'] >= 2)]
    R('R3', 'ciclo y próxima compra coherentes', 'PASA' if not mal else 'FALLA', f'{len(mal)} filas incoherentes' + (f" (ej. {mal[0]['cuit']} {mal[0]['sku'][:30]})" if mal else ''))
    raros = [r['estado'] for r in q(db, 'SELECT DISTINCT estado FROM rec_sku') if r['estado'] not in ESTADOS_REC]
    R('R4', 'estados conocidos', 'PASA' if not raros else 'FALLA', ', '.join(raros) or 'todos conocidos')
    fantasma = uno(db, "SELECT count(*) FROM rec_cliente k WHERE NOT EXISTS (SELECT 1 FROM limpia_renglones r JOIN limpia_comprobantes c ON c.tid=r.tid "
                       "WHERE c.cuit=k.cuit AND c.tipo='FA' AND r.clase='producto' AND r.cantidad_neta > 0.0001 AND c.fecha >= k.ultima)")
    R('R5', 'la última compra es una compra firme (no anulada)', 'PASA' if not fantasma else 'FALLA', f'{fantasma} clientes con última compra que no existe')
    inc = 0
    for k in q(db, 'SELECT cuit, estado FROM rec_cliente'):
        es = [r['estado'] for r in q(db, 'SELECT estado FROM rec_sku WHERE cuit=?', [k['cuit']])]
        mejor = min(es, key=lambda e: URG.index(e) if e in URG else 99)
        if (URG.index(k['estado']) if k['estado'] in URG else 99) != (URG.index(mejor) if mejor in URG else 99):
            inc += 1
    R('R6', 'el resumen por cliente muestra su SKU más urgente', 'PASA' if not inc else 'FALLA', f'{inc} clientes con resumen distinto')


def controles_cuentas(db, R):
    n, d = uno(db, 'SELECT count(*) FROM cue_cuentas'), uno(db, 'SELECT count(DISTINCT clave) FROM cue_cuentas')
    R('C1', 'una fila por cuenta', 'PASA' if n == d and n else 'FALLA', f'{n} filas · {d} claves')
    # la regla D07 se sigue pudiendo leer: leída con código propio, sin usar el motor
    t = (q(db, "SELECT texto FROM k_regla WHERE id='D07'") or [{'texto': ''}])[0]['texto'] or ''
    def lista(k):
        m = re.search(k + r'\s*\(([^)]*)\)', t, re.I)
        return [p for p in re.split(r'[,/;]', m.group(1)) if p.strip()] if m else []
    np_, ov = lista('no prospectar'), lista('otro vendedor')
    R('C2', 'la regla D07 se puede leer', 'PASA' if len(np_) >= 5 and len(ov) >= 2 else 'FALLA', f'{len(np_)} no prospectar · {len(ov)} otro vendedor')
    excl = uno(db, "SELECT count(*) FROM cue_cuentas WHERE estado IN ('no_prospectar','otro_vendedor')")
    R('C3', 'hay cuentas excluidas por la regla', 'PASA' if excl >= len(np_) // 2 else 'AVISO', f'{excl} cuentas excluidas para {len(np_) + len(ov)} nombres en la regla')
    con = q(db, 'SELECT empresa, conflicto FROM cue_cuentas WHERE conflicto IS NOT NULL')
    R('C4', 'conflictos entre fuentes para definir', 'AVISO' if con else 'PASA', '; '.join(f"{c['empresa']}: {c['conflicto'][:80]}" for c in con) or 'ninguno')
    falta = uno(db, "SELECT count(DISTINCT cuit) FROM limpia_comprobantes WHERE cuit <> '' AND cuit NOT IN (SELECT coalesce(cuit,'') FROM cue_cuentas)")
    R('C5', 'todo CUIT que compró tiene su cuenta', 'PASA' if not falta else 'FALLA', f'{falta} CUIT sin cuenta')
    mal = uno(db, "SELECT count(*) FROM cue_cuentas WHERE (estado = 'trabajar') <> (trabajar = 1)")
    R('C6', 'trabajar coincide con el estado', 'PASA' if not mal else 'FALLA', f'{mal} filas incoherentes')


CONTROLES = {'limpieza': controles_limpieza, 'recompra': controles_recompra, 'cuentas': controles_cuentas}


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
    # recompra: tablas sanas y después una última compra que no existe en las compras firmes
    c.executescript(f"""
     DELETE FROM limpia_comprobantes; INSERT INTO limpia_comprobantes VALUES('1','2026-10-01','FA','X');
     ALTER TABLE limpia_comprobantes ADD COLUMN cuit; UPDATE limpia_comprobantes SET cuit='30';
     INSERT INTO dc_corridas VALUES(3,'recompra','finnegans','','','OK','','','[]',NULL);
     CREATE TABLE rec_sku(cuit, cliente, sku, ultimo_modelo, linea, compras, primera, ultima, dias_desde_ultima, ciclo_dias, proxima, cant_prom, cant_ult, cant_total, estado, excluida);
     INSERT INTO rec_sku VALUES('30','X','Ont','Ont','FiberHome',2,'2026-09-01','2026-10-01',54,30,'2026-10-31',3,3,6,'Le toca',0);
     CREATE TABLE rec_cliente(cuit, cliente, estado, foco_sku, ciclo_dias, ultima, proxima, skus, skus_le_toca, skus_atrasados, excluida, calculado);
     INSERT INTO rec_cliente VALUES('30','X','Le toca','Ont',30,'2026-10-01','2026-10-31',1,1,0,0,'2026-11-24');
    """)
    c.commit()
    a4 = run(3)
    c.execute("UPDATE rec_cliente SET ultima='2026-11-15'"); c.commit()
    a5 = run(3)
    c.close()
    casos = [
        ('datos sanos: PASA', 'AUDITOR PASA' in a1.stdout),
        ('escribir fuera de contrato: FALLA', 'AUDITOR FALLA' in a2.stdout and 'ventas' in a2.stdout),
        ('falta un comprobante del R10: FALLA en L2', 'FALLA L2' in a3.stdout),
        ('NC suelta: FALLA en L3', 'FALLA L3' in a3.stdout),
        ('recompra sana: PASA', 'AUDITOR PASA' in a4.stdout and 'R3' in a4.stdout),
        ('recompra con una última compra que no existe: FALLA en R5', 'FALLA R5' in a5.stdout),
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
