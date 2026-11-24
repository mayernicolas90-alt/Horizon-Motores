#!/usr/bin/env python3
"""importar.py · Filtro de limpieza de reportes de Finnegans (0.3, 23/11/2026)

0.3: (1) las cuentas ajenas (otro vendedor, no prospectar, cuentas fuera) salen del CRM (--crm, obligatorio), no de una
     lista fija: la 0.2 marcaba Swissnet y Luna Net, que son de Nicolás, y no marcaba TPP. (2) Reporte incompleto = FALLA:
     si a los renglones les falta más del 2 % de los comprobantes de la cabecera hasta su corte, no se usa ni se sube
     (caso 23/11: GIANNINA3 con 468 de 873 comprobantes, sin Nodo Net, Iplus, Reltid ni Luna Net). Salida 1 = FALLA.

Arma una base limpia de compras firmes antes de que la usen los motores (recompra, carriles, Stockfish).
NO escribe en Turso ni en el CRM: deja una base SQLite local (mismo formato que Turso) y un resumen.

Fuentes (todas opcionales salvo --renglones):
  --renglones  CSV de Análisis de Facturación por renglón (TransaccionID, CUIT, producto). Se puede repetir:
               el primero manda; los siguientes solo suman comprobantes que no estén.
  --extra      JSON lines de la tabla ventas de Loki (sin TransaccionID): solo para fechas posteriores al
               corte de los renglones. Se vincula al TransaccionID por la cabecera.
  --cabecera   CSV de comprobantes de venta cabecera (FA/NC/ND con TransaccionID): control de faltantes.
  --pedidos    CSV de pedidos de venta cabecera: pedidos sin factura = pendientes de confirmar.

Qué hace:
  1. Identifica cada comprobante por TransaccionID (el número de comprobante se repite entre facturas y ND).
     Subir dos veces el mismo archivo no duplica nada.
  2. Solo HORIZON TRADING S.A. (Sur Technology y Presupuesto quedan fuera: D06).
  3. Clasifica: factura, NC, ND, diferencia de cambio (no es compra), anticipo (no es compra), no producto.
  4. Vincula cada NC con su factura: referencia escrita (FC 1665, 00005-00001605) > mismo cliente, producto y
     cantidad con un solo candidato > dos facturas idénticas (se desempata por nombre exacto) > a revisar.
     Una NC parcial descuenta solo su cantidad. Una NC solo de importe (descuento, ajuste) no toca cantidades.
  5. Compras firmes = renglones de factura con cantidad neta > 0 después de descontar sus NC.
  6. Control con la cabecera: comprobantes que existen y no tienen renglones.
  7. Pedidos sin factura vinculada (cliente + monto, hasta 90 días) = pendientes de confirmar.
  8. Guarda la fecha de corte de cada fuente.

Uso:
  python3 -I importar.py --base salida.sqlite --renglones R14.csv --renglones R24.csv \
      --extra loki_ventas.jsonl --cabecera R22.csv --pedidos R19.csv --crm <export CRM> [--desde 2024-01-01]
"""
import argparse, collections, csv, datetime as D, hashlib, json, os, re, sqlite3, sys, unicodedata

VERSION = 'importar 0.3 · 2026-11-23'
EMPRESA = 'HORIZON TRADING S.A.'
TOL_DESCUENTO = 0.05   # pedido vs. factura con descuento contado (Sampacho 19/11: 1.256 → 1.218,32)
TABLAS = ('fuentes', 'comprobantes', 'renglones', 'vinculos_nc', 'revisar', 'faltan_renglones', 'pedidos')
NOPROD = re.compile(r'descuento|anticipo|intereses|servicios? admin|gastos de admin|flete|licencia|hi-care|'
                    r'series basic sw|upgrade rtu|diferencia de cambio|honorarios|muestras? de producto', re.I)
ANTICIPO = re.compile(r'anticipo', re.I)
MAX_FALTAN = 0.02      # 0.3: si a los renglones les falta más del 2 % de los comprobantes de la cabecera (hasta su corte), FALLA
# 0.3: las cuentas que no son de Nicolás (otro vendedor o fuera) salen del CRM, no de una lista fija (la 0.2 marcaba
# Swissnet y Luna Net, que son de Nicolás, y no marcaba TPP). Se marcan, no se borran.
SUFIJOS = re.compile(r'\b(s ?a ?s|s ?r ?l|s ?a ?u|s ?a|s ?a ?p ?e ?m|ltda|limitada|cv)\b')


def clave_nombre(s):
    return re.sub(r'\s+', ' ', SUFIJOS.sub(' ', re.sub(r'[^a-z0-9 ]', ' ', norm(s)))).strip()


class Ajenas:
    """Cuentas que no son de Nicolás, por CUIT (D03) y, solo si el comprobante no trae CUIT, por nombre.
    Fuente: fichas del CRM (otroVendedor, noProspectar) + datacenter/restricciones (cuentasFuera; cuentasDeNicolas manda)."""

    def __init__(self, crm):
        self.cuit, self.nombre, self.propias = {}, {}, set()
        ops = os.path.join(crm or '', 'oportunidades')
        if not crm or not os.path.isdir(ops) or not os.listdir(ops):
            raise SystemExit('FALLA · falta --crm con oportunidades/ (export del CRM): sin las marcas de otro vendedor '
                             'y cuentas fuera no se corre con listas vacías.')
        def cuits(o):
            return {dig(x) for x in [o.get('cuit'), o.get('facturacionId')] +
                    [c.get('cuit') if isinstance(c, dict) else c for c in (o.get('cuitsAdicionales') or [])] if len(dig(x)) in (8, 11)}
        self.fichas = 0
        for f in sorted(os.listdir(ops)):
            if not f.endswith('.json'):
                continue
            o = json.load(open(os.path.join(ops, f), encoding='utf-8'))
            o = o.get('data', o) if isinstance(o.get('data'), dict) else o
            self.fichas += 1
            motivo = ('otro vendedor' if o.get('otroVendedor') in (True, 'si') else
                      'no prospectar' if o.get('noProspectar') == 'si' else None)
            if motivo:
                for c in cuits(o):
                    self.cuit[c] = motivo
                if o.get('empresa'):
                    self.nombre[clave_nombre(o['empresa'])] = motivo
        rp = os.path.join(crm, 'datacenter', 'restricciones.json')
        if os.path.exists(rp):
            r = json.load(open(rp, encoding='utf-8'))
            r = r.get('data', r) if isinstance(r.get('data'), dict) else r
            for v in (r.get('cuentasFuera') or {}).values():
                if len(dig(v.get('cuit'))) == 11:
                    self.cuit[dig(v['cuit'])] = 'cuenta fuera'
                if v.get('empresa'):
                    self.nombre[clave_nombre(v['empresa'])] = 'cuenta fuera'
            for v in (r.get('cuentasDeNicolas') or {}).values():
                if len(dig(v.get('cuit'))) == 11:
                    self.propias.add(dig(v['cuit']))
        self.por_nombre = {}   # nombre del comprobante -> CUIT (lo aprende de los renglones)

    def aprender(self, cliente, cuit):
        if cliente and len(dig(cuit)) in (8, 11):
            self.por_nombre.setdefault(clave_nombre(cliente), dig(cuit))

    def es(self, cliente, cuit=None):
        c = dig(cuit) or self.por_nombre.get(clave_nombre(cliente), '')
        if c:
            if c in self.propias:
                return 0
            if c in self.cuit:
                return 1
        return int(clave_nombre(cliente) in self.nombre)


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', s).strip()


def dig(s):
    return re.sub(r'\D', '', str(s or ''))


def num(s):
    try:
        return float(str(s).replace(',', '.')) if s not in (None, '') else 0.0
    except ValueError:
        return 0.0


def leer_csv(p):
    raw = open(p, 'rb').read()
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return list(csv.DictReader(txt.splitlines(), delimiter=';')), hashlib.sha256(raw).hexdigest()


def tipo_doc(doc):
    d = norm(doc)
    if 'dif. cambio' in d or 'dif cambio' in d:
        return 'DC'
    if 'credito' in d:
        return 'NC'
    if 'debito' in d:
        return 'ND'
    if 'factura' in d:
        return 'FA'
    return 'OTRO'


def nro_comp(c):
    m = re.search(r'([AB])-?0*(\d+)-0*(\d+)', str(c or ''))
    return (m.group(1), int(m.group(2)), int(m.group(3))) if m else None


def refs_factura(texto):
    """Números de factura citados en la descripción de una NC: 'FC 1665', 'Anula FC 00005-00001605', 'FC A-0002-00000782'."""
    t = str(texto or '')
    out = [(int(pv), int(n)) for pv, n in re.findall(r'(\d{4,5})-(\d{6,8})', t)]
    if not out:
        out = [(None, int(n)) for n in re.findall(r'(?:FC|FAC|FACT\w*|factura)\s*[A-B]?\s*-?\s*0*(\d{2,8})', t, re.I)]
    return out


# ---------------------------------------------------------------- base
VISTA = ('SELECT c.cuit, c.cliente, c.fecha, c.comprobante, c.tid, r.producto, r.marca, r.familia, r.subfamilia, '
         'r.cantidad AS cantidad_facturada, r.cantidad_neta, c.otro_vendedor '
         "FROM {p}renglones r JOIN {p}comprobantes c ON c.tid = r.tid "
         "WHERE c.tipo = 'FA' AND r.clase = 'producto' AND r.cantidad_neta > 0.0001")
ESQUEMA = """
CREATE TABLE fuentes(fuente TEXT, archivo TEXT, sha256 TEXT, filas INTEGER, desde TEXT, corte TEXT, uso TEXT);
CREATE TABLE comprobantes(tid TEXT PRIMARY KEY, fecha TEXT, tipo TEXT, documento TEXT, comprobante TEXT, cliente TEXT,
  cuit TEXT, descripcion TEXT, motivo TEXT, fuente TEXT, otro_vendedor INTEGER);
CREATE TABLE renglones(id INTEGER PRIMARY KEY, tid TEXT, producto TEXT, producto_n TEXT, clase TEXT, cantidad REAL,
  cantidad_neta REAL, marca TEXT, familia TEXT, subfamilia TEXT, moneda TEXT);
CREATE TABLE vinculos_nc(nc_tid TEXT, factura_tid TEXT, metodo TEXT, alcance TEXT);
CREATE TABLE revisar(tid TEXT, fecha TEXT, cliente TEXT, motivo TEXT, detalle TEXT, otro_vendedor INTEGER);
CREATE TABLE faltan_renglones(tid TEXT, fecha TEXT, documento TEXT, comprobante TEXT, cliente TEXT, otro_vendedor INTEGER);
CREATE TABLE pedidos(nro TEXT PRIMARY KEY, fecha TEXT, cliente TEXT, factura_tid TEXT, estado TEXT, usuario TEXT);
"""



def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--subir-turso', action='store_true', help='copia el resultado a la base de Loki como tablas limpia_* (solo con hacelo)')
    ap.add_argument('--loki', help='ruta a loki_sql.py (por defecto, junto a este archivo)')
    ap.add_argument('--renglones', action='append', required=True)
    ap.add_argument('--extra')
    ap.add_argument('--cabecera')
    ap.add_argument('--pedidos')
    ap.add_argument('--desde', default='2024-01-01')
    ap.add_argument('--crm', help='carpeta del export del CRM (ArtifactData out_dir): oportunidades/ y datacenter/restricciones.json')
    ap.add_argument('--max-faltan', type=float, default=MAX_FALTAN,
                    help='proporción máxima de comprobantes de la cabecera sin renglones (hasta el corte) antes de dar FALLA')
    a = ap.parse_args(argv)
    AJ = Ajenas(a.crm)

    if os.path.exists(a.base):
        os.remove(a.base)
    db = sqlite3.connect(a.base)
    db.executescript(ESQUEMA)
    db.execute('CREATE VIEW compras_firmes AS ' + VISTA.format(p=''))
    resumen = collections.Counter()

    comp, lineas = {}, collections.defaultdict(list)   # tid -> cabecera ; tid -> renglones

    # 1. renglones (el primero manda)
    corte_renglones = None
    for i, p in enumerate(a.renglones):
        filas, sha = leer_csv(p)
        if not filas or 'TransaccionID' not in filas[0]:
            sys.exit(f'{p}: no tiene TransaccionID; no se puede usar como renglones')
        fk = 'Fecha comprobante' if 'Fecha comprobante' in filas[0] else 'Fecha'
        nuevos = set()
        for r in filas:
            if (r.get('Empresa') or EMPRESA) != EMPRESA:
                continue
            f = (r.get(fk) or '')[:10]
            if f < a.desde:
                continue
            tid = r['TransaccionID']
            if tid in comp and tid not in nuevos:
                continue          # ya lo trajo una fuente anterior: no se duplica
            nuevos.add(tid)
            cuit_r = r.get('Nrodeidentificacion') or r.get('Nro de identificación') or ''   # 0.3: el export viejo trae el otro encabezado
            AJ.aprender(r.get('Cliente'), cuit_r)
            comp.setdefault(tid, dict(tid=tid, fecha=f, tipo=tipo_doc(r.get('Documento')), documento=r.get('Documento'),
                                      comprobante=r.get('Comprobante'), cliente=(r.get('Cliente') or '').strip(),
                                      cuit=dig(cuit_r), descripcion=r.get('Descripción') or '',
                                      motivo=r.get('Motivodeanulacion') or r.get('Motivo de anulación') or '', fuente=os.path.basename(p)))
            lineas[tid].append(dict(producto=r.get('Producto') or '', cantidad=num(r.get('Cantidad')), marca=r.get('Marca') or '',
                                    familia=r.get('Familia') or '', subfamilia=r.get('Subfamilia') or r.get('SubFamilia') or '', moneda=r.get('Moneda') or ''))
        fechas = [(r.get(fk) or '')[:10] for r in filas if r.get(fk)]
        corte = max(fechas) if fechas else None
        if i == 0:
            corte_renglones = corte
        db.execute('INSERT INTO fuentes VALUES(?,?,?,?,?,?,?)', ('renglones', os.path.basename(p), sha, len(filas),
                   min(fechas) if fechas else None, corte, 'base' if i == 0 else 'suma comprobantes que faltan'))
        resumen[f'comprobantes de {os.path.basename(p)}'] = len(nuevos)

    # cabecera: mapa (documento normalizado, número) -> tid, para la fuente extra y el control
    cab, cab_idx = [], {}
    if a.cabecera:
        cab, sha = leer_csv(a.cabecera)
        for r in cab:
            cab_idx[(norm(r['Documento']), r['Nro comp'], norm(r['Cliente']))] = r
        fs = [r['Fecha'][:10] for r in cab]
        db.execute('INSERT INTO fuentes VALUES(?,?,?,?,?,?,?)', ('cabecera', os.path.basename(a.cabecera), sha, len(cab), min(fs), max(fs), 'control'))

    # 2. extra (Loki ventas) solo después del corte de los renglones
    if a.extra:
        extra = [json.loads(l) for l in open(a.extra, encoding='utf-8') if l.strip()]
        sumados = 0
        for r in extra:
            if r.get('empresa') != EMPRESA or not corte_renglones or r['fecha'] <= corte_renglones:
                continue
            c = cab_idx.get((norm(r['documento']), r['comprobante'], norm(r['cliente'])))
            if not c:
                db.execute('INSERT INTO revisar VALUES(?,?,?,?,?,?)', (None, r['fecha'], r['cliente'], 'renglón de Loki sin cabecera',
                           f"{r['documento']} {r['comprobante']}", AJ.es(r['cliente'], r.get('cuit'))))
                continue
            tid = c['TransaccionID']
            if tid in comp and comp[tid]['fuente'] != 'loki':
                continue
            if tid not in comp:
                sumados += 1
            comp.setdefault(tid, dict(tid=tid, fecha=r['fecha'], tipo=tipo_doc(r['documento']), documento=r['documento'],
                                      comprobante=r['comprobante'], cliente=r['cliente'].strip(), cuit=dig(r.get('cuit')),
                                      descripcion=c.get('Descripción') or '', motivo='', fuente='loki'))
            lineas[tid].append(dict(producto=r['producto'] or '', cantidad=num(r['cantidad']), marca=r.get('marca') or '',
                                    familia=r.get('familia') or '', subfamilia=r.get('subfamilia') or '', moneda=r.get('moneda') or ''))
        fs = [r['fecha'] for r in extra]
        db.execute('INSERT INTO fuentes VALUES(?,?,?,?,?,?,?)', ('extra', os.path.basename(a.extra), None, len(extra), min(fs) if fs else None,
                   max(fs) if fs else None, f'solo después del {corte_renglones}'))
        resumen['comprobantes sumados desde Loki'] = sumados

    # 3. clasificar renglones
    for tid, ls in lineas.items():
        c = comp[tid]
        for l in ls:
            l['producto_n'] = norm(l['producto'])
            if c['tipo'] == 'DC':
                l['clase'] = 'dif_cambio'
            elif ANTICIPO.search(l['producto']):
                l['clase'] = 'anticipo'
            elif NOPROD.search(l['producto']):
                l['clase'] = 'no_producto'
            else:
                l['clase'] = 'producto'
            l['neta'] = abs(l['cantidad']) if c['tipo'] == 'FA' else 0.0

    # 4. vincular NC
    facturas = [t for t, c in comp.items() if c['tipo'] == 'FA']
    por_nro = collections.defaultdict(list)
    for t in facturas:
        n = nro_comp(comp[t]['comprobante'])
        if n:
            por_nro[(comp[t]['cuit'], n[2])].append((n[1], t))

    def descontar(nc_tid, fa_tid):
        """Descuenta las cantidades de la NC de los renglones de la factura (por producto). Devuelve el alcance."""
        resto = 0.0
        for l in lineas[nc_tid]:
            if l['clase'] not in ('producto', 'anticipo'):
                continue
            q = abs(l['cantidad'])
            for f in lineas[fa_tid]:
                if q <= 0:
                    break
                if f['producto_n'] == l['producto_n'] and f['neta'] > 0:
                    d = min(q, f['neta'])
                    f['neta'] -= d
                    q -= d
            resto += q
        quedan = sum(f['neta'] for f in lineas[fa_tid] if f['clase'] in ('producto', 'anticipo'))
        return 'total' if quedan <= 0.0001 else 'parcial', resto

    ncs = sorted((t for t, c in comp.items() if c['tipo'] == 'NC'), key=lambda t: comp[t]['fecha'])
    for t in ncs:
        c = comp[t]
        prod = [l for l in lineas[t] if l['clase'] in ('producto', 'anticipo')]
        ov = AJ.es(c['cliente'], c['cuit'])
        # a) referencia escrita
        cand = []
        for pv, n in refs_factura(c['descripcion']):
            for fpv, ft in por_nro.get((c['cuit'], n), []):
                if pv is None or pv == fpv:
                    cand.append(ft)
        cand = list(dict.fromkeys(cand))
        if len(cand) == 1:
            alc, _ = descontar(t, cand[0]) if prod else ('importe', 0)
            db.execute('INSERT INTO vinculos_nc VALUES(?,?,?,?)', (t, cand[0], 'referencia', alc))
            resumen['NC por referencia'] += 1
            continue
        if not prod:
            resumen['NC solo de importe (descuento o ajuste)'] += 1
            db.execute('INSERT INTO vinculos_nc VALUES(?,?,?,?)', (t, None, 'solo importe', 'importe'))
            continue
        # b) mismo cliente, producto y cantidad
        def alcanza(ft):
            disp = collections.Counter()
            for f in lineas[ft]:
                disp[f['producto_n']] += f['neta']
            need = collections.Counter()
            for l in prod:
                need[l['producto_n']] += abs(l['cantidad'])
            return all(disp[k] >= v - 0.0001 for k, v in need.items())
        cand = [ft for ft in facturas if comp[ft]['cuit'] == c['cuit'] and comp[ft]['fecha'] <= c['fecha'] and alcanza(ft)]
        metodo = None
        if len(cand) == 1:
            metodo = 'producto y cantidad'
        elif len(cand) > 1:
            firmas = {tuple(sorted((f['producto_n'], f['neta']) for f in lineas[ft] if f['clase'] == 'producto')) for ft in cand}
            if len(firmas) == 1:
                # facturas idénticas: el resultado en cantidades es el mismo; se desempata por nombre exacto y luego la más vieja
                exactos = [ft for ft in cand if {l['producto'] for l in prod} <= {f['producto'] for f in lineas[ft]}]
                cand = sorted(exactos or cand, key=lambda ft: comp[ft]['fecha'])[:1]
                metodo = 'facturas idénticas'
        if metodo:
            alc, _ = descontar(t, cand[0])
            db.execute('INSERT INTO vinculos_nc VALUES(?,?,?,?)', (t, cand[0], metodo, alc))
            resumen['NC por ' + metodo] += 1
        else:
            db.execute('INSERT INTO revisar VALUES(?,?,?,?,?,?)', (t, c['fecha'], c['cliente'], 'NC sin factura clara',
                       f"{len(cand)} candidatas · {c['descripcion'][:60]}", ov))
            resumen['NC a revisar' + (' (otro vendedor)' if ov else '')] += 1

    # 5. guardar
    for t, c in comp.items():
        db.execute('INSERT INTO comprobantes VALUES(?,?,?,?,?,?,?,?,?,?,?)', (t, c['fecha'], c['tipo'], c['documento'], c['comprobante'],
                   c['cliente'], c['cuit'], c['descripcion'], c['motivo'], c['fuente'], AJ.es(c['cliente'], c['cuit'])))
        for l in lineas[t]:
            db.execute('INSERT INTO renglones(tid,producto,producto_n,clase,cantidad,cantidad_neta,marca,familia,subfamilia,moneda) '
                       'VALUES(?,?,?,?,?,?,?,?,?,?)', (t, l['producto'], l['producto_n'], l['clase'], l['cantidad'],
                       round(l['neta'], 4), l['marca'], l['familia'], l['subfamilia'], l['moneda']))

    # 6. control con la cabecera (0.3: hasta el corte de los renglones mide completitud; después del corte solo informa)
    falla = []
    if cab:
        en_corte = faltan_corte = 0
        for r in cab:
            if (r.get('Empresa') or EMPRESA) != EMPRESA or r['Fecha'][:10] < a.desde or tipo_doc(r['Documento']) == 'DC':
                continue
            dentro = bool(corte_renglones) and r['Fecha'][:10] <= corte_renglones
            en_corte += dentro
            if r['TransaccionID'] in comp:
                continue
            ov = AJ.es(r['Cliente'])
            db.execute('INSERT INTO faltan_renglones VALUES(?,?,?,?,?,?)', (r['TransaccionID'], r['Fecha'][:10], r['Documento'], r['Nro comp'], r['Cliente'], ov))
            if dentro:
                faltan_corte += 1
                resumen['comprobantes sin renglones' + (' (cuenta ajena)' if ov else '')] += 1
            else:
                resumen['comprobantes posteriores al corte de los renglones (se esperan en la próxima carga)'] += 1
        prop = faltan_corte / en_corte if en_corte else 0.0
        if prop > a.max_faltan:
            falla.append(f'a los renglones les faltan {faltan_corte} de {en_corte} comprobantes de la cabecera hasta el '
                         f'{corte_renglones} ({prop:.1%} > {a.max_faltan:.0%}): el reporte vino incompleto (¿filtro de cliente o '
                         f'«Visualizar todas» sin tildar?). No se usa.')
    elif a.subir_turso:
        falla.append('sin --cabecera no se puede controlar que los renglones estén completos: no se sube.')

    # 7. pedidos sin factura
    if a.pedidos and cab:
        ped, sha = leer_csv(a.pedidos)
        fs = [r['Fecha'][:10] for r in ped]
        db.execute('INSERT INTO fuentes VALUES(?,?,?,?,?,?,?)', ('pedidos', os.path.basename(a.pedidos), sha, len(ped), min(fs), max(fs), 'pendientes'))
        fac = collections.defaultdict(list)
        for r in cab:
            if tipo_doc(r['Documento']) == 'FA':
                fac[norm(r['Cliente'])].append(r)
        peds = [p for p in ped if p['Fecha'][:10] >= a.desde]
        # todas las parejas posibles (mismo cliente, mismo monto, factura entre 3 días antes y 90 después);
        # se asignan de la más cercana en fecha a la más lejana, una factura por pedido
        parejas = []
        for p in peds:
            fp = D.date.fromisoformat(p['Fecha'][:10])
            for f in fac.get(norm(p['Cliente']), []):
                if abs(num(f['Bruto']) - num(p['Bruto'])) > 1:
                    continue
                d = (D.date.fromisoformat(f['Fecha'][:10]) - fp).days
                if -3 <= d <= 90:
                    parejas.append((abs(d), p['Nro comp'], f['TransaccionID']))
        asignado, usadas = {}, set()
        for d, pn, ft in sorted(parejas):
            if pn not in asignado and ft not in usadas:
                asignado[pn] = ft
                usadas.add(ft)
        # 0.2: segunda pasada para el descuento contado (la factura sale hasta 5 % por debajo del pedido, en 30 días)
        con_desc, parejas = set(), []
        for p in peds:
            if p['Nro comp'] in asignado:
                continue
            fp, bp = D.date.fromisoformat(p['Fecha'][:10]), num(p['Bruto'])
            for f in fac.get(norm(p['Cliente']), []):
                if f['TransaccionID'] in usadas or not (0 < bp - num(f['Bruto']) <= bp * TOL_DESCUENTO):
                    continue
                d = (D.date.fromisoformat(f['Fecha'][:10]) - fp).days
                if -3 <= d <= 30:
                    parejas.append((abs(d), p['Nro comp'], f['TransaccionID']))
        for d, pn, ft in sorted(parejas):
            if pn not in asignado and ft not in usadas:
                asignado[pn] = ft
                usadas.add(ft)
                con_desc.add(pn)
        for p in sorted(peds, key=lambda r: r['Fecha']):
            m = asignado.get(p['Nro comp'])
            est = ('facturado con descuento' if p['Nro comp'] in con_desc else 'facturado') if m else 'pendiente de confirmar'
            db.execute('INSERT INTO pedidos VALUES(?,?,?,?,?,?)', (p['Nro comp'], p['Fecha'][:10], p['Cliente'], m, est, p.get('Nombreusuarioalta')))
            resumen['pedidos ' + est if m else 'pedidos sin factura vinculada'] += 1

    db.commit()
    q = lambda s: db.execute(s).fetchone()[0]
    print(f'{VERSION} · base {a.base}')
    for r in db.execute('SELECT fuente, archivo, desde, corte, uso FROM fuentes'):
        print(f'  fuente {r[0]:9} {r[1][:28]:28} {r[2]} → {r[3]}  ({r[4]})')
    n_comp = q('SELECT count(*) FROM comprobantes')
    n_tipo = dict(db.execute('SELECT tipo, count(*) FROM comprobantes GROUP BY tipo').fetchall())
    n_firmes = q('SELECT count(*) FROM compras_firmes')
    n_anul = q("SELECT count(*) FROM renglones r JOIN comprobantes c ON c.tid=r.tid "
               "WHERE c.tipo='FA' AND r.clase='producto' AND r.cantidad_neta<=0.0001")
    n_ant = q("SELECT count(*) FROM renglones WHERE clase='anticipo'")
    print(f"  comprobantes {n_comp} · facturas {n_tipo.get('FA', 0)} · NC {n_tipo.get('NC', 0)} · ND {n_tipo.get('ND', 0)}"
          f" · dif. cambio {n_tipo.get('DC', 0)}")
    print(f'  renglones de compra firmes {n_firmes} · renglones anulados del todo {n_anul} · renglones de anticipo {n_ant}')
    for k, v in sorted(resumen.items()):
        print(f'  {k}: {v}')
    print(f'  cuentas ajenas desde el CRM: {len(AJ.cuit)} CUIT ({AJ.fichas} fichas leídas) · propias por dictado: {len(AJ.propias)}')
    db.close()
    if falla:
        for f in falla:
            print('  ✗ ' + f)
        print('Importador: FALLA')
        resumen['_falla'] = len(falla)
        return resumen
    print('Importador: PASA')
    if a.subir_turso:
        subir_turso(a.base, a.loki)
    return resumen


# ---------------------------------------------------------------- Turso (base de Loki)
def subir_turso(base, loki=None):
    """Copia las tablas de la base limpia a la base de Loki como limpia_* (se rehacen enteras en cada carga:
    son tablas derivadas). No toca ninguna otra tabla."""
    import importlib.util
    ruta = loki or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'loki_sql.py')
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    L = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(L)
    src = sqlite3.connect(base)
    dst = L.conectar()
    st = []
    for t in TABLAS:
        cols = src.execute(f'PRAGMA table_info({t})').fetchall()
        defs = ', '.join(f'{c[1]} {c[2] or "TEXT"}' for c in cols)
        st += [(f'DROP TABLE IF EXISTS limpia_{t}', []), (f'CREATE TABLE limpia_{t}({defs})', [])]
        marcas = ', '.join('?' * len(cols))
        st += [(f'INSERT INTO limpia_{t} VALUES({marcas})', list(r)) for r in src.execute(f'SELECT * FROM {t}')]
    st += [('DROP VIEW IF EXISTS limpia_compras_firmes', []),
           ('CREATE VIEW limpia_compras_firmes AS ' + VISTA.format(p='limpia_'), [])]
    dst.run(st)
    n = {t: dst.run([(f'SELECT count(*) FROM limpia_{t}', [])])[0][1][0][0] for t in TABLAS}
    dst.close()
    print('  Turso: ' + ' · '.join(f'limpia_{t} {v}' for t, v in n.items()))


# ---------------------------------------------------------------- autotest (sin datos reales)
def autotest():
    import tempfile
    d = tempfile.mkdtemp()
    def esc(nombre, cols, filas):
        p = os.path.join(d, nombre)
        with open(p, 'w', encoding='utf-8', newline='') as fh:
            w = csv.writer(fh, delimiter=';')
            w.writerow(cols)
            w.writerows(filas)
        return p
    RC = ['TransaccionID', 'Fecha', 'Documento', 'Comprobante', 'Cliente', 'Nrodeidentificacion', 'Descripción', 'Motivodeanulacion',
          'Producto', 'Cantidad', 'Marca', 'Familia', 'Subfamilia', 'Moneda', 'Empresa']
    FA, NC, DC, H = 'Factura de Venta Electrónica', 'Nota de Crédito de Ventas Electrónica', 'Nota de Débito de Ventas por Dif. Cambio', EMPRESA
    ren = [
        # 1 anulada entera por referencia (caso Redtel)
        ['1', '2026-08-01', FA, 'A-00005-00001010', 'Cliente X', '30-11111111-1', '', '', 'Ont A', '60', 'FH', 'FTTH', 'ONU', 'Dólares', H],
        ['2', '2026-08-25', NC, 'A-00005-00000020', 'Cliente X', '30-11111111-1', 'Devolucion FC 1010', 'ANULACIÓN', 'Ont A', '-60', 'FH', 'FTTH', 'ONU', 'Dólares', H],
        # 2 dos facturas iguales y una NC sin referencia: se anula la de nombre exacto (caso Full Sat)
        ['3', '2026-10-15', FA, 'A-00005-00001020', 'Cliente Y', '30-22222222-2', '', '', 'Ont B ', '300', 'FH', 'FTTH', 'ONU', 'Dólares', H],
        ['4', '2026-10-20', FA, 'A-00005-00001021', 'Cliente Y', '30-22222222-2', '', '', 'Ont B', '300', 'FH', 'FTTH', 'ONU', 'Dólares', H],
        ['5', '2026-11-11', NC, 'A-00005-00000021', 'Cliente Y', '30-22222222-2', '', 'DIFERENCIA DE CAMBIO FCE', 'Ont B ', '-300', 'FH', 'FTTH', 'ONU', 'Dólares', H],
        # 3 anticipo anulado y factura final (caso Rosario)
        ['6', '2026-10-28', FA, 'A-00005-00001030', 'Cliente Z', '30-33333333-3', '', '', 'Anticipo de Mercadería', '1', '', '', '', 'Dólares', H],
        ['7', '2026-11-11', NC, 'A-00005-00000022', 'Cliente Z', '30-33333333-3', '', '', 'Anticipo de Mercadería', '-1', '', '', '', 'Dólares', H],
        ['8', '2026-11-11', FA, 'A-00005-00001031', 'Cliente Z', '30-33333333-3', '', '', 'Chasis', '4', 'HW', 'FTTH', 'OLT', 'Dólares', H],
        # 4 NC parcial por referencia
        ['9', '2026-09-01', FA, 'A-00005-00001040', 'Cliente W', '30-44444444-4', '', '', 'Caja', '10', 'FH', 'ODN', 'CTO', 'Dólares', H],
        ['10', '2026-09-10', NC, 'A-00005-00000023', 'Cliente W', '30-44444444-4', 'Anula FC 00005-00001040 parcial', '', 'Caja', '-4', 'FH', 'ODN', 'CTO', 'Dólares', H],
        # 5 diferencia de cambio, otra empresa y fecha vieja: no son compras
        ['11', '2026-09-15', DC, 'A-00005-00001010', 'Cliente W', '30-44444444-4', '', '', 'Diferencia de cambio', '1', '', '', '', 'Pesos', H],
        ['12', '2026-09-15', FA, 'A-00012-00000001', 'Cliente W', '30-44444444-4', '', '', 'Caja', '5', '', '', '', 'Dólares', 'SUR TECHNOLOGY S.A.'],
        ['13', '2023-05-01', FA, 'A-00005-00000500', 'Cliente W', '30-44444444-4', '', '', 'Caja', '5', '', '', '', 'Dólares', H],
        # 6 NC de producto sin factura posible: a revisar
        ['14', '2026-06-01', NC, 'A-00005-00000024', 'Cliente V', '30-55555555-5', '', '', 'Ont C', '-5', '', '', '', 'Dólares', H],
    ]
    # 7 (0.3) Swissnet es de Nicolás: la lista fija de la 0.2 la marcaba como otro vendedor
    ren.append(['15', '2026-10-01', FA, 'A-00005-00001050', 'Swissnet SRL', '30-66666666-6', '', '', 'Drop', '1000', 'FH', 'FIBRA OPTICA', 'DROP', 'Dólares', H])
    r1 = esc('ren.csv', RC, ren)
    crm = os.path.join(d, 'crm')
    os.makedirs(os.path.join(crm, 'oportunidades')); os.makedirs(os.path.join(crm, 'datacenter'))
    def ficha(i, o):
        json.dump(o, open(os.path.join(crm, 'oportunidades', i + '.json'), 'w', encoding='utf-8'))
    ficha('y', dict(empresa='Cliente Y', cuit='30-22222222-2', otroVendedor=True))           # otro vendedor (caso TPP)
    ficha('w', dict(empresa='Cliente W', cuit='30-44444444-4', noProspectar='si'))           # dictado: es de Nicolás
    ficha('s', dict(empresa='Swissnet', cuit='30-66666666-6'))
    json.dump(dict(cuentasFuera={'v': dict(cuit='30555555555', empresa='Cliente V')},
                   cuentasDeNicolas={'w': dict(cuit='30444444444', empresa='Cliente W')}),
              open(os.path.join(crm, 'datacenter', 'restricciones.json'), 'w', encoding='utf-8'))
    cab = esc('cab.csv', ['TransaccionID', 'Fecha', 'Documento', 'Nro comp', 'Cliente', 'Bruto', 'Descripción'], [
        ['4', '2026-10-20', FA, 'A-00005-00001021', 'Cliente Y', '100', ''],
        ['9', '2026-09-01', FA, 'A-00005-00001040', 'Cliente W', '970', ''],
        ['99', '2026-11-01', FA, 'A-00005-00001099', 'Cliente U', '50', '']])
    ped = esc('ped.csv', ['Fecha', 'Nro comp', 'Cliente', 'Bruto', 'Nombreusuarioalta'], [
        ['2026-10-19', 'P-1', 'Cliente Y', '100', 'x'], ['2026-08-30', 'P-2', 'Cliente W', '1000', 'x'], ['2026-11-10', 'P-3', 'Cliente T', '10', 'x']])
    base = os.path.join(d, 'b.sqlite')
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        res1 = main(['--base', base, '--renglones', r1, '--cabecera', cab, '--pedidos', ped, '--crm', crm])
    db = sqlite3.connect(base)
    ajena = lambda tid: db.execute('SELECT otro_vendedor FROM comprobantes WHERE tid=?', (tid,)).fetchone()[0]
    firme = lambda tid: db.execute('SELECT coalesce(sum(cantidad_neta),0) FROM compras_firmes WHERE tid=?', (tid,)).fetchone()[0]
    vinc = lambda nc: db.execute('SELECT factura_tid, metodo, alcance FROM vinculos_nc WHERE nc_tid=?', (nc,)).fetchone()
    ped_e = lambda n: db.execute('SELECT estado FROM pedidos WHERE nro=?', (n,)).fetchone()[0]
    casos = [
        ('NC con referencia anula la factura entera', firme('1') == 0 and vinc('2') == ('1', 'referencia', 'total')),
        ('dos facturas iguales: se anula la de nombre exacto y queda la otra', firme('3') == 0 and firme('4') == 300 and vinc('5')[1] == 'facturas idénticas'),
        ('anticipo no es compra; la factura final sí', firme('6') == 0 and firme('8') == 4),
        ('NC parcial descuenta solo su cantidad', firme('9') == 6 and vinc('10') == ('9', 'referencia', 'parcial')),
        ('diferencia de cambio, otra empresa y fechas viejas quedan fuera',
         db.execute("SELECT count(*) FROM comprobantes WHERE tid IN ('12','13')").fetchone()[0] == 0 and
         db.execute("SELECT tipo FROM comprobantes WHERE tid='11'").fetchone()[0] == 'DC'),
        ('NC sin factura posible va a revisar', db.execute("SELECT count(*) FROM revisar WHERE tid='14'").fetchone()[0] == 1),
        ('comprobante de la cabecera sin renglones se avisa', db.execute("SELECT count(*) FROM faltan_renglones WHERE tid='99'").fetchone()[0] == 1),
        ('pedido con factura del mismo monto', ped_e('P-1') == 'facturado'),
        ('pedido con descuento contado (hasta 5 %)', ped_e('P-2') == 'facturado con descuento'),
        ('pedido sin factura queda pendiente', ped_e('P-3') == 'pendiente de confirmar'),
        ('0.3 otro vendedor sale de la ficha del CRM (caso TPP)', ajena('3') == 1 and ajena('4') == 1),
        ('0.3 Swissnet es de Nicolás: no se marca como ajena', ajena('15') == 0),
        ('0.3 cuenta fuera por CUIT desde restricciones', db.execute("SELECT otro_vendedor FROM revisar WHERE tid='14'").fetchone()[0] == 1),
        ('0.3 cuentasDeNicolas manda sobre noProspectar', ajena('9') == 0),
        ('0.3 reporte incompleto (1 de 3 sin renglones) da FALLA', bool(res1.get('_falla'))),
    ]
    db.close()
    base2 = os.path.join(d, 'b2.sqlite')
    with contextlib.redirect_stdout(io.StringIO()):
        main(['--base', base2, '--renglones', r1, '--renglones', r1, '--cabecera', cab, '--pedidos', ped, '--crm', crm])
    a_, b_ = sqlite3.connect(base), sqlite3.connect(base2)
    igual = all(a_.execute(f'SELECT * FROM {t} ORDER BY 1').fetchall() == b_.execute(f'SELECT * FROM {t} ORDER BY 1').fetchall()
                for t in ('comprobantes', 'vinculos_nc', 'pedidos')) and \
        a_.execute('SELECT count(*) FROM renglones').fetchone() == b_.execute('SELECT count(*) FROM renglones').fetchone()
    casos.append(('subir dos veces el mismo archivo no duplica nada', igual))
    cab_ok = esc('cab_ok.csv', ['TransaccionID', 'Fecha', 'Documento', 'Nro comp', 'Cliente', 'Bruto', 'Descripción'], [
        ['4', '2026-10-20', FA, 'A-00005-00001021', 'Cliente Y', '100', ''], ['9', '2026-09-01', FA, 'A-00005-00001040', 'Cliente W', '970', ''],
        ['98', '2026-11-20', FA, 'A-00005-00001098', 'Cliente U', '50', '']])
    with contextlib.redirect_stdout(io.StringIO()):
        res3 = main(['--base', os.path.join(d, 'b3.sqlite'), '--renglones', r1, '--cabecera', cab_ok, '--crm', crm])
    casos.append(('0.3 completo hasta el corte da PASA (lo posterior al corte solo se informa)', not res3.get('_falla')))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            main(['--base', os.path.join(d, 'b4.sqlite'), '--renglones', r1])
        sin_crm = False
    except SystemExit as e:
        sin_crm = 'FALLA' in str(e)
    casos.append(('0.3 sin --crm no corre (no hay listas vacías)', sin_crm))
    ok = sum(1 for _, c in casos if c)
    for t, c in casos:
        print(('  OK   ' if c else '  FALLA ') + t)
    print(f'autotest importar: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    if '--autotest' in sys.argv:
        sys.exit(autotest())
    sys.exit(1 if main().get('_falla') else 0)
