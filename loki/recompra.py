#!/usr/bin/env python3
"""recompra.py 4.0 · motor Recompra del datacenter (24/11/2026, DEC-1124a/b). Solo biblioteca estándar.

Recompra por cliente (CUIT) + SKU sobre las compras limpias del motor Limpieza (limpia_renglones + limpia_comprobantes).
Las reglas de negocio son las de la v3.1 (09-13/11), que leía el R10 crudo y neteaba las notas de crédito por su cuenta:
  · líneas vigentes FiberHome / Ousent / Huawei / ZTT (HW sin Cisco = Huawei; HW Cisco = HFC discontinuado)
  · las ONT/ONU FiberHome se miden juntas (el cliente cambia de modelo, no deja de comprar); ONU Huawei = reemplazo por FH,
    y «Ya migró a FH» si compró ONT FiberHome después
  · switches S5735/S6730 = campaña, fuera del motor · marcas discontinuadas = reemplazo
  · compras a menos de 15 días = una sola compra (entregas partidas) · ciclo = mediana de días entre compras
  · estados: Le toca (de 15 días antes a 30 después de la próxima) · Atrasado (hasta el doble del ciclo o 180 días) · Se fue
    · En ciclo · Sin ciclo (1 compra) · Dormido (1 compra y más de 540 días)
Lo que cambia en la 4.0: la fuente (compras ya limpias: NC vinculadas a su factura, sin anticipos ni diferencias de cambio)
y la salida (tablas rec_sku y rec_cliente en Turso en lugar de Excel/JSON). Calcula para todos los clientes y marca con
«excluida» las cuentas de otros vendedores según la lista de la v3.1: el que usa el resultado decide.

Uso (python3 -I): recompra.py --contrato · recompra.py --autotest · recompra.py correr [--loki ruta] [--hoy AAAA-MM-DD]
                  recompra.py simular [--hoy AAAA-MM-DD]   (calcula sin escribir y muestra el JSON)
"""
import datetime as D, importlib.util, json, os, re, statistics, sys

VERSION = 'recompra 4.0 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
NOPROS = ['pogliotti', 'itsa', 'amma', 'mutual mercantil', 'obercom', 'wiltel', 'gigared', 'astesano', 'generaci', 'itc comunic',
          'ax internet', 'fibrazo', 'tv music', 'support internet', 'itelsa', 'comworks',
          'fesacom', 'sur technology', 'presupuesto horizon', 'horizon trading']
EXACTOS = {'itel s.a.', 'sion s.a.'}
VIG = {'FiberHome', 'Ousent', 'Huawei', 'ZTT'}
DISC = {'I-con', 'Zte', 'ZTE', 'Netconn', 'Intelbras', 'Cisco', 'Compal', 'Arris', 'Wolk', 'China Mobile'}
CISCO = re.compile(r'UBR|ESR|C7200|CMTS|ERB', re.I)
NOPROD = re.compile(r'Hi-Care|Series Basic SW|upgrade RTU|Intereses|Servicios Admin|Gastos de Admin|Anticipo|Flete|Licencia|Descuento', re.I)
ONT = re.compile(r'^(Ont|Onu)\b', re.I)
SWITCH = re.compile(r'^Switch S5735|^Switch S6730', re.I)
ORDEN = {'Le toca': 0, 'Atrasado': 1, 'Se fue': 2, 'Reemplazo (ONU Huawei → FH)': 3, 'Sin ciclo (1 compra)': 4, 'En ciclo': 5,
         'Reemplazo (discontinuado)': 6, 'Sin marca (revisar)': 6, 'Otra marca': 6, 'Ya migró a FH': 7,
         'Switch (campaña, fuera del motor)': 7, 'Dormido': 8}
CONTRATO = {'id': 'recompra', 'nombre': 'Recompra', 'disparo': 'finnegans', 'lee': ['limpia_renglones', 'limpia_comprobantes'],
            'escribe': ['rec_sku', 'rec_cliente'],
            'que_hace': 'Ciclo de compra por cliente y SKU sobre las compras limpias: le toca, atrasado, se fue, reemplazo.'}
COLS_SKU = ['cuit', 'cliente', 'sku', 'ultimo_modelo', 'linea', 'compras', 'primera', 'ultima', 'dias_desde_ultima', 'ciclo_dias',
            'proxima', 'cant_prom', 'cant_ult', 'cant_total', 'estado', 'excluida']
COLS_CLI = ['cuit', 'cliente', 'estado', 'foco_sku', 'ciclo_dias', 'ultima', 'proxima', 'skus', 'skus_le_toca', 'skus_atrasados', 'excluida', 'calculado']


def fd(s):
    return D.date.fromisoformat(s[:10])


def linea(marca, prod):
    if marca in VIG:
        return marca
    if marca == 'HW':
        return 'HFC disc' if CISCO.search(prod) else 'Huawei'
    return 'otra'


def excluida(cli):
    c = cli.lower().strip()
    return c in EXACTOS or any(k in c for k in NOPROS)


def calcular(renglones, hoy):
    """renglones: dicts {cuit, cliente, fecha, tid, producto, marca, cantidad_neta} de compras firmes. Devuelve (skus, clientes)."""
    hoy = fd(hoy)
    nombre, grupos, marca_de = {}, {}, {}
    for r in sorted(renglones, key=lambda r: (r['fecha'], int(re.sub(r'\D', '', str(r['tid'])) or 0))):
        prod, marca = (r['producto'] or '').strip(), (r['marca'] or '').strip()
        if not r['cuit'] or (r['cantidad_neta'] or 0) <= 0 or NOPROD.search(prod):
            continue
        lin = linea(marca, prod)
        fam = ('ONT FiberHome (cualquier modelo)' if lin == 'FiberHome' else 'ONU Huawei → reemplazo FH' if lin == 'Huawei' else prod) if ONT.search(prod) else prod
        nombre[r['cuit']] = (r['cliente'] or '').strip()
        marca_de[(r['cuit'], fam)] = marca
        grupos.setdefault((r['cuit'], fam, lin), []).append({'fecha': fd(r['fecha']), 'cant': float(r['cantidad_neta']), 'modelo': prod,
                                                             'switch': bool(SWITCH.search(prod))})
    skus = []
    for (cuit, fam, lin), vivas in grupos.items():
        ev = []
        for x in vivas:
            if ev and (x['fecha'] - ev[-1]['f0']).days < 15:
                ev[-1]['cant'] += x['cant']; ev[-1]['f'] = x['fecha']; ev[-1]['modelo'] = x['modelo']
            else:
                ev.append({'f0': x['fecha'], 'f': x['fecha'], 'cant': x['cant'], 'modelo': x['modelo']})
        fechas = [e['f0'] for e in ev]
        n, ult = len(ev), ev[-1]['f']
        dias_ult = (hoy - ult).days
        ciclo = int(statistics.median([(b - a).days for a, b in zip(fechas, fechas[1:])])) if n >= 2 else None
        if any(x['switch'] for x in vivas):
            estado = 'Switch (campaña, fuera del motor)'
        elif fam.startswith('ONU Huawei'):
            estado = 'Reemplazo (ONU Huawei → FH)'
        elif lin not in VIG and lin != 'Huawei':
            mc = marca_de.get((cuit, fam), '')
            estado = 'Reemplazo (discontinuado)' if (lin == 'HFC disc' or mc in DISC) else ('Sin marca (revisar)' if mc == '' else 'Otra marca')
        elif ciclo is None:
            estado = 'Sin ciclo (1 compra)' if dias_ult <= 540 else 'Dormido'
        else:
            atraso = (hoy - (ult + D.timedelta(days=ciclo))).days
            estado = 'En ciclo' if atraso < -15 else 'Le toca' if atraso <= 30 else 'Atrasado' if dias_ult <= max(2 * ciclo, 180) else 'Se fue'
        cants = [e['cant'] for e in ev]
        skus.append(dict(cuit=cuit, cliente=nombre[cuit], sku=fam, ultimo_modelo=ev[-1]['modelo'], linea=lin, compras=n,
                         primera=fechas[0].isoformat(), ultima=ult.isoformat(), dias_desde_ultima=dias_ult, ciclo_dias=ciclo,
                         proxima=(ult + D.timedelta(days=ciclo)).isoformat() if ciclo else None,
                         cant_prom=round(sum(cants) / n), cant_ult=round(cants[-1]), cant_total=round(sum(cants)), estado=estado,
                         excluida=int(excluida(nombre[cuit]))))
    # ONU Huawei ya migradas a ONT FH no son reemplazo
    fh = {s['cuit']: s['ultima'] for s in skus if s['sku'].startswith('ONT FiberHome')}
    for s in skus:
        if s['estado'] == 'Reemplazo (ONU Huawei → FH)' and s['cuit'] in fh and fh[s['cuit']] > s['ultima']:
            s['estado'] = 'Ya migró a FH'
    skus.sort(key=lambda s: (ORDEN.get(s['estado'], 9), s['dias_desde_ultima']))
    clientes = []
    for cuit in sorted({s['cuit'] for s in skus}):
        ss = [s for s in skus if s['cuit'] == cuit]
        f = ss[0]
        clientes.append(dict(cuit=cuit, cliente=f['cliente'], estado=f['estado'], foco_sku=f['sku'], ciclo_dias=f['ciclo_dias'],
                             ultima=max(s['ultima'] for s in ss), proxima=f['proxima'], skus=len(ss),
                             skus_le_toca=sum(s['estado'] == 'Le toca' for s in ss), skus_atrasados=sum(s['estado'] == 'Atrasado' for s in ss),
                             excluida=f['excluida'], calculado=hoy.isoformat()))
    return skus, clientes


def loki(ruta=None):
    ruta = ruta or os.path.join(AQUI, 'loki_sql.py')
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def leer(db):
    cols, filas = db.run([("SELECT c.cuit, c.cliente, c.fecha, c.tid, r.producto, r.marca, r.cantidad_neta FROM limpia_renglones r "
                           "JOIN limpia_comprobantes c ON c.tid = r.tid WHERE c.tipo = 'FA' AND r.clase = 'producto' AND r.cantidad_neta > 0.0001", [])])[0]
    return [dict(zip(cols, f)) for f in filas]


def escribir(db, skus, clientes):
    st = [('DROP TABLE IF EXISTS rec_sku', []), ('DROP TABLE IF EXISTS rec_cliente', []),
          ('CREATE TABLE rec_sku(' + ', '.join(COLS_SKU) + ')', []), ('CREATE TABLE rec_cliente(' + ', '.join(COLS_CLI) + ')', [])]
    st += [('INSERT INTO rec_sku VALUES(' + ','.join('?' * len(COLS_SKU)) + ')', [s[c] for c in COLS_SKU]) for s in skus]
    st += [('INSERT INTO rec_cliente VALUES(' + ','.join('?' * len(COLS_CLI)) + ')', [c[k] for k in COLS_CLI]) for c in clientes]
    db.run(st)


def resumen(skus, clientes):
    est = {}
    for s in skus:
        if not s['excluida']:
            est[s['estado']] = est.get(s['estado'], 0) + 1
    return {'skus': len(skus), 'clientes': len(clientes), 'por_estado': est}


# ---------------------------------------------------------------- autotest (sin datos reales)
def autotest():
    hoy = '2026-11-24'
    R = lambda cuit, cli, f, prod, marca, q, tid=1: dict(cuit=cuit, cliente=cli, fecha=f, tid=tid, producto=prod, marca=marca, cantidad_neta=q)
    ren = [
        # A: ONT FH cada ~30 días, cambia de modelo; entrega partida a 5 días = una compra; última 25/10 → le toca
        R('1', 'Cliente A', '2026-07-27', 'Ont Gpon HG6145F3', 'FiberHome', 100), R('1', 'Cliente A', '2026-08-26', 'Ont Gpon HG6145F3', 'FiberHome', 100),
        R('1', 'Cliente A', '2026-09-25', 'Ont Gpon HG6543D', 'FiberHome', 50), R('1', 'Cliente A', '2026-09-30', 'Ont Gpon HG6543D', 'FiberHome', 50),
        R('1', 'Cliente A', '2026-10-25', 'Ont Gpon HG6543D', 'FiberHome', 80),
        # B: cada ~30 días, última 03/03 (266 días > 180) → se fue · C: cada 30 días, última 05/09 (próxima 05/10, 50 días tarde, 80 días) → atrasado
        R('2', 'Cliente B', '2026-01-02', 'Caja FitDP', 'FiberHome', 10), R('2', 'Cliente B', '2026-02-01', 'Caja FitDP', 'FiberHome', 10),
        R('2', 'Cliente B', '2026-03-03', 'Caja FitDP', 'FiberHome', 10),
        R('3', 'Cliente C', '2026-07-07', 'Drop', 'ZTT', 5), R('3', 'Cliente C', '2026-08-06', 'Drop', 'ZTT', 5), R('3', 'Cliente C', '2026-09-05', 'Drop', 'ZTT', 5),
        # D: ONU Huawei y después ONT FH → ya migró · E: ONU Huawei sola → reemplazo
        R('4', 'Cliente D', '2026-03-01', 'Onu EG8145V5', 'HW', 20), R('4', 'Cliente D', '2026-09-01', 'Ont Gpon HG6145F3', 'FiberHome', 20),
        R('5', 'Cliente E', '2026-09-01', 'Onu EG8145V5', 'HW', 20),
        # F: switch · G: marca discontinuada · H: compra única reciente · I: compra única vieja · J: otro vendedor
        R('6', 'Cliente F', '2026-10-01', 'Switch S5735-L', 'HW', 1), R('7', 'Cliente G', '2026-10-01', 'Ont X', 'I-con', 10),
        R('8', 'Cliente H', '2026-10-01', 'Cable ADSS', 'FiberHome', 1000), R('9', 'Cliente I', '2024-01-10', 'Cable ADSS', 'FiberHome', 1000),
        R('10', 'Comworks SA', '2026-10-01', 'Ont Gpon HG6145F3', 'FiberHome', 500),
        # no son compras: descuento y cantidad 0 (anulada por NC en Limpieza)
        R('1', 'Cliente A', '2026-10-25', 'Descuento Comercial', '', 1), R('2', 'Cliente B', '2026-11-20', 'Caja FitDP', 'FiberHome', 0),
    ]
    skus, cli = calcular(ren, hoy)
    S = lambda cuit, sku=None: next((s for s in skus if s['cuit'] == cuit and (sku is None or s['sku'] == sku)), None)
    a = S('1')
    casos = [
        ('ONT FiberHome juntas aunque cambie el modelo', a['sku'] == 'ONT FiberHome (cualquier modelo)' and a['ultimo_modelo'] == 'Ont Gpon HG6543D'),
        ('entrega partida a menos de 15 días = una compra', a['compras'] == 4 and a['cant_total'] == 380),
        ('ciclo = mediana de días entre compras; le toca', a['ciclo_dias'] == 30 and a['proxima'] == '2026-11-24' and a['estado'] == 'Le toca'),
        ('pasado el doble del ciclo y 180 días: se fue', S('2')['estado'] == 'Se fue'),
        ('atrasado dentro de los 180 días', S('3')['estado'] == 'Atrasado'),
        ('ONU Huawei con ONT FH después: ya migró', S('4', 'ONU Huawei → reemplazo FH')['estado'] == 'Ya migró a FH'),
        ('ONU Huawei sola: reemplazo', S('5')['estado'] == 'Reemplazo (ONU Huawei → FH)'),
        ('switch fuera del motor', S('6')['estado'] == 'Switch (campaña, fuera del motor)'),
        ('marca discontinuada: reemplazo', S('7')['estado'] == 'Reemplazo (discontinuado)'),
        ('compra única: sin ciclo o dormido', S('8')['estado'] == 'Sin ciclo (1 compra)' and S('9')['estado'] == 'Dormido'),
        ('otro vendedor queda calculado y marcado excluida', S('10')['excluida'] == 1),
        ('descuentos y cantidades anuladas no son compras', not any(s['sku'].startswith('Descuento') for s in skus) and S('2')['ultima'] == '2026-03-03'),
        ('resumen por cliente: el estado más urgente primero', next(c for c in cli if c['cuit'] == '1')['estado'] == 'Le toca'),
    ]
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    ok = sum(1 for _, x in casos if x)
    print(f'autotest recompra: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    arg = lambda k, dflt=None: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else dflt
    hoy = arg('--hoy', D.date.today().isoformat())
    if '--autotest' in a:
        sys.exit(autotest())
    if '--contrato' in a:
        print(json.dumps(dict(CONTRATO, version=VERSION), ensure_ascii=False))
        sys.exit(0)
    if a[:1] in (['correr'], ['simular']):
        db = loki(arg('--loki')).conectar()
        skus, cli = calcular(leer(db), hoy)
        if a[0] == 'correr':
            escribir(db, skus, cli)
        db.close()
        if a[0] == 'simular':
            print(json.dumps(skus, ensure_ascii=False, default=str))
        print('RESUMEN ' + json.dumps(resumen(skus, cli), ensure_ascii=False))
        sys.exit(0)
    print(__doc__)
