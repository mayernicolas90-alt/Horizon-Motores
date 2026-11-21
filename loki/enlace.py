"""Enlace cotización → pedido → factura → remito · v0.1.0 (21/11/2026) · cantidades por renglón, venta neta.

importar DB   : lee R24 (pedidos), R10 (facturas) y R26 (remitos) de la base de Loki y los guarda por renglón.
                Clave única (tipo, comprobante, código): procesar el mismo archivo dos veces no duplica nada.
                Cada renglón guarda fecha del hecho, fecha en que Loki lo supo y el archivo de origen (sha256).
enlazar DB    : une cada renglón con la cotización del CRM (mismo CUIT, fecha, mismo producto) y calcula por línea
                cotizado / pedido / facturado / remitido / pendiente. Lo dudoso queda marcado, con su motivo.
ver DB NM     : la línea de tiempo de una cotización.
--autotest    : casos sin datos reales (venta neta con nota de crédito y devolución; doble importación).
Venta neta = factura − nota de crédito; las devoluciones de venta restan lo entregado (D06, lección L-venta-neta).
Solo lee la base de Loki; escribe únicamente en la base SQLite que se le pasa."""
import sys, os, csv, io, json, hashlib, sqlite3, collections, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def q(sql, args=()):
    from bitacora2 import turso   # se importa recién al usar la base: el autotest no la necesita
    return turso(sql, args)

HOY = dt.date.today().isoformat()
DESDE = '2026-08-01'
DDL = """
CREATE TABLE IF NOT EXISTS comprobante (tipo TEXT, numero TEXT, cod TEXT, fecha TEXT, cuit TEXT, cliente TEXT, cantidad REAL, pendiente REAL,
  origen TEXT, origen_sha TEXT, conocido TEXT, PRIMARY KEY (tipo, numero, cod));
CREATE TABLE IF NOT EXISTS vinculo (cotizacion TEXT, nm TEXT, tipo TEXT, numero TEXT, cod TEXT, cantidad REAL, estado TEXT, motivo TEXT,
  PRIMARY KEY (cotizacion, tipo, numero, cod));
"""


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def cuit(x):
    d = ''.join(ch for ch in (x or '') if ch.isdigit())
    return f'{d[:2]}-{d[2:10]}-{d[10:]}' if len(d) == 11 else None


def ncod(c):
    c = (c or '').strip().upper()
    return c[5:] if c.startswith('LOCAL') else c


def norm(s):
    import unicodedata, re
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def importar(db):
    db.executescript(DDL)
    n0 = db.execute('SELECT COUNT(*) FROM comprobante').fetchone()[0]
    arch = {r['nombre']: r for r in q("SELECT nombre, texto FROM archivos WHERE nombre IN ('R24.csv','R26.csv','R25.csv')")}
    sha = {k: hashlib.sha256(v['texto'].encode()).hexdigest()[:12] for k, v in arch.items()}
    filas = collections.defaultdict(lambda: [0.0, 0.0])
    meta = {}
    # pedidos
    rows = list(csv.reader(io.StringIO(arch['R24.csv']['texto']), delimiter=';')); h = {c: i for i, c in enumerate(rows[0])}
    for r in rows[1:]:
        if r[h['Empresa']].strip() == 'HORIZON TRADING S.A.' and r[h['Fecha']][:10] >= DESDE:
            k = ('pedido', r[h['Comprobante']], ncod(r[h['Cod. Producto']]))
            filas[k][0] += f(r[h['Cantidad']]); filas[k][1] += f(r[h['Pendiente Destino']])
            meta[k] = (r[h['Fecha']][:10], cuit(r[h['Nro de identificación']]), r[h['Cliente']], 'R24.csv', sha['R24.csv'])
    # facturas (R10 ya cargado en la tabla ventas)
    c10 = q("SELECT sha256 FROM cargas WHERE fuente='R10' ORDER BY cargado DESC LIMIT 1")[0]['sha256'][:12]
    for r in q(f"SELECT comprobante, documento, fecha, cuit, cliente, cod_producto, cantidad, pte_dest FROM ventas WHERE empresa='HORIZON TRADING S.A.' AND fecha >= '{DESDE}' AND documento NOT LIKE '%ébito%'"):
        k = ('nc' if 'rédito' in (r.get('documento') or '') else 'factura', r['comprobante'], ncod(r['cod_producto']))
        filas[k][0] += f(r['cantidad']); filas[k][1] += f(r['pte_dest'])
        meta[k] = (r['fecha'][:10], r['cuit'], r['cliente'], 'R10', c10)
    # remitos: R26 no trae CUIT → por alias de cliente
    alias = {}
    for a in q('SELECT alias, cuit FROM cliente_alias'):
        alias.setdefault(norm(a['alias']), set()).add(a['cuit'])
    pid_nom = {}
    for l in arch['R25.csv']['texto'].splitlines()[1:]:
        p = l.split(';')
        if len(p) > 2:
            pid_nom.setdefault(norm(p[2]), ncod(p[1]))
    rows = list(csv.reader(io.StringIO(arch['R26.csv']['texto']), delimiter=';')); h = {c: i for i, c in enumerate(rows[0])}
    for r in rows[1:]:
        sub = r[h['Transacconsubtiponombre']]
        if r[h['Fecha']][:10] < DESDE or not ('Remito' in sub or 'Devoluci' in sub):
            continue
        cs = alias.get(norm(r[h['Cliente']]), set())
        k = ('devolucion' if 'Devoluci' in sub else 'remito', r[h['Comprobante']] or ('DEV-' + r[h['Fecha']][:10] + '-' + norm(r[h['Cliente']])[:20]), pid_nom.get(norm(r[h['Producto']]), norm(r[h['Producto']])))
        filas[k][0] += f(r[h['Cantidad']]); filas[k][1] += f(r[h['Pendiente']])
        meta[k] = (r[h['Fecha']][:10], next(iter(cs)) if len(cs) == 1 else None, r[h['Cliente']], 'R26.csv', sha['R26.csv'])
    for k, (cant, pend) in filas.items():
        fe, cu, cl, o, s = meta[k]
        # INSERT OR IGNORE + UPDATE: misma clave = mismo renglón; el «conocido» queda con la primera vez que Loki lo vio
        db.execute('INSERT OR IGNORE INTO comprobante VALUES (?,?,?,?,?,?,?,?,?,?,?)', (*k, fe, cu, cl, cant, pend, o, s, HOY))
        db.execute('UPDATE comprobante SET cantidad=?, pendiente=?, origen_sha=? WHERE tipo=? AND numero=? AND cod=?', (cant, pend, s, *k))
    db.commit()
    return n0, db.execute('SELECT COUNT(*) FROM comprobante').fetchone()[0]


def enlazar(db):
    db.executescript(DDL)
    PID = {}
    for l in q("SELECT texto FROM archivos WHERE nombre='R25.csv'")[0]['texto'].splitlines()[1:]:
        p = l.split(';')
        if len(p) > 1:
            PID[p[0].strip()] = ncod(p[1])
    cots = {c['id']: c for c in q("SELECT id, numero, cuit, estado, archivada, fecha FROM crm_cotizacion WHERE estado <> 'borrador'")}
    lin = collections.defaultdict(float)
    for it in q('SELECT cotizacion_id, codigo, cantidad FROM crm_cotizacion_item'):
        if it['cotizacion_id'] in cots and it['codigo']:
            lin[(it['cotizacion_id'], PID.get(str(it['codigo']).strip(), ncod(str(it['codigo']))))] += f(it['cantidad'])
    db.execute('DELETE FROM vinculo')
    comp = [(t, n, c, f, cu, abs(ca)) for t, n, c, f, cu, ca in db.execute('SELECT tipo, numero, cod, fecha, cuit, cantidad FROM comprobante WHERE cuit IS NOT NULL').fetchall()]
    por_comp = collections.defaultdict(list)
    for tipo, num, cod, fe, cu, cant in comp:
        for (cid, c_cod), qc in lin.items():
            c = cots[cid]
            if c['cuit'] != cu or c_cod != cod or not c['fecha']:
                continue
            d = (dt.date.fromisoformat(fe) - dt.date.fromisoformat(c['fecha'][:10])).days
            if -7 <= d <= (240 if tipo in ('nc', 'devolucion') else 150):
                por_comp[(tipo, num, cod)].append((d, cid, qc, cant))
    # asignación en orden de fecha: cada comprobante consume la cantidad que le queda a la cotización para ese paso
    resto = collections.defaultdict(float)
    for (cid, c_cod), qc in lin.items():
        for t in ('pedido', 'factura', 'remito', 'nc', 'devolucion'):
            resto[(cid, c_cod, t)] = qc
    fechas = {(t, n, c): fe for t, n, c, fe, cu, ca in comp}
    devuelta = collections.defaultdict(bool)
    for (t, n, c), cands in por_comp.items():
        if t in ('nc', 'devolucion'):
            for x in cands:
                devuelta[x[1]] = True
    for (tipo, num, cod) in sorted(por_comp, key=lambda k: (fechas[k], k)):
        cands = sorted(por_comp[(tipo, num, cod)])
        vivos = [x for x in cands if resto[(x[1], cod, tipo)] > 0 and x[0] >= -7]
        if not vivos:
            continue
        # la cotización más reciente anterior al comprobante; si no hay, la más cercana
        prev = [x for x in vivos if x[0] >= 0]
        d, cid, qc, cant = min(prev, key=lambda x: x[0]) if prev else min(vivos, key=lambda x: abs(x[0]))
        c = cots[cid]
        asign = min(cant, resto[(cid, cod, tipo)])
        resto[(cid, cod, tipo)] -= asign
        otros = [x for x in vivos if x[1] != cid and x[0] >= 0 and abs(x[0] - d) <= 3]
        motivos = []
        if otros:
            motivos.append('también podría ser ' + ', '.join(cots[x[1]]['numero'] or x[1] for x in otros[:2]))
        if c['estado'] in ('rechazada', 'perdida') and not devuelta.get(cid):
            motivos.append(f"la cotización figura {c['estado']} en el CRM")
        if c['archivada'] == '1':
            motivos.append('la cotización está archivada en el CRM')
        if cant > asign + 0.01:
            motivos.append(f'el comprobante trae {cant:g}: {cant - asign:g} no corresponden a esta cotización')
        db.execute('INSERT OR REPLACE INTO vinculo VALUES (?,?,?,?,?,?,?,?)',
                   (cid, c['numero'], tipo, num, cod, asign, 'dudoso' if motivos else 'ok', '; '.join(motivos)))
    db.commit()
    return lin, cots


def linea(tot):
    """Totales de una línea de cotización → venta neta y lo que queda por entregar."""
    neta = tot.get('factura', 0) - tot.get('nc', 0)
    entregado = max(0, tot.get('remito', 0) - tot.get('devolucion', 0))
    return {'neta': neta, 'por_entregar': max(0, neta - entregado)}


def totales(db, cid):
    t = collections.defaultdict(float)
    for tipo, cant, est in db.execute('SELECT tipo, cantidad, estado FROM vinculo WHERE cotizacion=?', (cid,)):
        t[tipo] += cant
        t['dudoso'] += est == 'dudoso'
    t.update(linea(t))
    return t


def ver(db, nm, lin, cots):
    cid = next((k for k, c in cots.items() if c['numero'] == nm), None)
    c = cots[cid]
    out = [f"{nm} · {c['estado']}{' archivada' if c['archivada'] == '1' else ''} · {c['fecha']}"]
    for (k, cod), qc in lin.items():
        if k != cid:
            continue
        v = db.execute('SELECT tipo, numero, cantidad, estado, motivo FROM vinculo WHERE cotizacion=? AND cod=? ORDER BY tipo', (cid, cod)).fetchall()
        tot = collections.defaultdict(float)
        for t, n, cant, e, m in v:
            tot[t] += cant
        pend_ent = db.execute("SELECT SUM(c.pendiente) FROM comprobante c JOIN vinculo v ON v.tipo=c.tipo AND v.numero=c.numero AND v.cod=c.cod WHERE v.cotizacion=? AND v.cod=? AND c.tipo='factura'", (cid, cod)).fetchone()[0] or 0
        out.append(f"  {cod}: cotizado {qc:g} · pedido {tot['pedido']:g} · facturado {tot['factura']:g} · nota de crédito {tot['nc']:g} · remitido {tot['remito']:g} · devuelto {tot['devolucion']:g} · venta neta {linea(tot)['neta']:g} · sin pedir {max(0, qc - max(tot['pedido'], tot['factura'])):g} · por entregar {linea(tot)['por_entregar']:g}")
        if pend_ent and tot['remito'] >= tot['factura'] > 0:
            out.append(f"    CONFLICTO DE FUENTES: el R10 dice {pend_ent:g} sin entregar, pero el R26 tiene remitos por {tot['remito']:g}")
        for t, n, cant, e, m in v:
            fe, o, s, kn = db.execute('SELECT fecha, origen, origen_sha, conocido FROM comprobante WHERE tipo=? AND numero=? AND cod=?', (t, n, cod)).fetchone()
            out.append(f"    {fe} {t} {n} · {cant:g} · {e.upper()}{(' · ' + m) if m else ''} · respaldo {o} {s} · Loki lo supo {kn}")
    return '\n'.join(out)


def autotest():
    """Datos inventados: una venta devuelta (factura + NC + devolución) y una entregada."""
    global q
    real = q
    R25 = 'ProductoID;Codigo;Producto' + chr(10) + '1114;FTTHONTHG6543D;Ont Gpon HG6543D' + chr(10)
    cots = [{'id': 'c1', 'numero': 'NMX1', 'cuit': '30-11111111-1', 'estado': 'rechazada', 'archivada': '0', 'fecha': '2026-08-27'},
            {'id': 'c2', 'numero': 'NMX2', 'cuit': '30-22222222-2', 'estado': 'aceptada', 'archivada': '0', 'fecha': '2026-11-12'}]
    items = [{'cotizacion_id': 'c1', 'codigo': '1114', 'cantidad': 150}, {'cotizacion_id': 'c2', 'codigo': '1114', 'cantidad': 30}]

    def falso(sql, args=()):
        if 'R25' in sql:
            return [{'texto': R25}]
        if 'FROM crm_cotizacion_item' in sql:
            return items
        if 'FROM crm_cotizacion' in sql:
            return cots
        raise AssertionError(sql)
    q = falso
    try:
        db = sqlite3.connect(':memory:')
        db.executescript(DDL)
        filas = [('pedido', 'P1', 'FTTHONTHG6543D', '2026-08-31', '30-11111111-1', 150), ('factura', 'F1', 'FTTHONTHG6543D', '2026-09-01', '30-11111111-1', 150),
                 ('nc', 'NC1', 'FTTHONTHG6543D', '2026-09-21', '30-11111111-1', -150), ('devolucion', 'D1', 'FTTHONTHG6543D', '2026-09-21', '30-11111111-1', 150),
                 ('factura', 'F2', 'FTTHONTHG6543D', '2026-11-12', '30-22222222-2', 30), ('remito', 'R2', 'FTTHONTHG6543D', '2026-11-19', '30-22222222-2', 30)]
        for _ in range(2):   # dos veces: no tiene que duplicar
            for t, n, c, fe, cu, ca in filas:
                db.execute('INSERT OR IGNORE INTO comprobante VALUES (?,?,?,?,?,?,?,?,?,?,?)', (t, n, c, fe, cu, 'x', ca, 0, 'test', 'test', '2026-11-21'))
        enlazar(db)
        t1, t2 = totales(db, 'c1'), totales(db, 'c2')
        casos = [('doble importación no duplica', db.execute('SELECT COUNT(*) FROM comprobante').fetchone()[0] == 6),
                 ('venta devuelta: neta 0', t1['neta'] == 0), ('venta devuelta: nada por entregar', t1['por_entregar'] == 0),
                 ('venta devuelta: no queda dudosa', t1['dudoso'] == 0), ('venta entregada: neta 30', t2['neta'] == 30),
                 ('venta entregada: nada por entregar', t2['por_entregar'] == 0)]
    finally:
        q = real
    mal = 0
    for nombre, ok in casos:
        mal += not ok
        print(f"{'PASA ' if ok else 'FALLA'} {nombre}")
    print(f"RESULTADO: {'PASA' if not mal else 'FALLA'} ({len(casos) - mal}/{len(casos)})")
    return 1 if mal else 0


if __name__ == '__main__':
    if sys.argv[1:] == ['--autotest']:
        sys.exit(autotest())
    db = sqlite3.connect(sys.argv[1])
    a = importar(db); b = importar(db)
    print(f'importación 1: {a[0]} → {a[1]} renglones · importación 2: {b[0]} → {b[1]} renglones · duplicados: {b[1] - a[1]}')
    lin, cots = enlazar(db)
    st = dict(db.execute('SELECT estado, COUNT(*) FROM vinculo GROUP BY estado').fetchall())
    print('vínculos:', st)
    for nm in sys.argv[2:]:
        print('\n' + ver(db, nm, lin, cots))
    print('\nDUDOSOS:')
    for r in db.execute("SELECT nm, tipo, numero, cod, cantidad, motivo FROM vinculo WHERE estado='dudoso' ORDER BY nm"):
        print('  ', ' · '.join(str(x) for x in r))
