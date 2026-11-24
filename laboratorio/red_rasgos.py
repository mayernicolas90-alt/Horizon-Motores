#!/usr/bin/env python3
"""red_rasgos.py 0.1 · laboratorio (24/11/2026) · tabla de rasgos para la red neuronal de Loki.

Reparto acordado en el buzón (para_PM_2026-11-24_f / para_CRM_2026-11-24_j): esta sesión arma los datos limpios y
los controla; la sesión Loki modela. Escribe solo sus tablas (DEC-1124a): red_rasgos y red_control.

Una fila por cliente (CUIT con compras firmes propias) y fecha de corte (cada 14 días desde 2024-07-01, más hoy):
  compras    · días desde la última, compras (eventos agrupados a 15 días) en 90/180/365 y total, unidades en 365,
               ciclo (mediana) y MAD, ratio y distancia a la próxima, mezcla ONU/cable/inversión, antigüedad, SKUs
  pedidos    · pedidos abiertos al corte (cargados ≤ corte y sin factura ≤ corte) y días desde el último pedido
  cuentas    · cue_trabajar, cue_estado (foto de hoy: es una decisión de Nicolás, no un dato que cambie con el tiempo)
  crm        · solo en el corte de hoy (crm_disponible=1): cotizaciones abiertas y vencidas, etapa, días sin contacto,
               historial en 30/90 días. En cortes viejos van NULL: el CRM no tiene historia y usarlos sería fuga.
  objetivo   · y30 / y60: compró en los 30 / 60 días siguientes (NULL si la ventana no está completa)
Control de fugas (red_control): todo dato usado en un corte tiene fecha ≤ corte. Si falla, no escribe red_rasgos.
Uso: python3 -I laboratorio/red_rasgos.py correr [--hoy AAAA-MM-DD] · --autotest
"""
import datetime as D, importlib.util, json, math, os, re, statistics, sys, unicodedata

VERSION = 'red_rasgos 0.1 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
INICIO, PASO, AGRUPAR = D.date(2024, 7, 1), 14, 15
ONU = re.compile(r'\b(ont|onu)\b|hg6\d{3}|an5506|eg8\d{3}|hs8\d{3}', re.I)
INVERSION = re.compile(r'\bolt\b|placa|switch|an6000|an5516|ma5800|rectificador|chasis', re.I)
CABLE = re.compile(r'cable|drop|fibra|adss|bobina', re.I)
ABIERTAS = {'enviada', 'borrador', 'espera_aprobacion', 'pendiente'}
COLS = ['corte', 'cuit', 'dias_ult', 'ev_90', 'ev_180', 'ev_365', 'ev_tot', 'unid_365', 'ciclo', 'mad', 'ratio_ciclo',
        'dist_prox', 'part_onu', 'part_cable', 'part_inv', 'antig', 'skus_365', 'ped_abiertos', 'dias_ult_pedido',
        'cue_trabajar', 'cue_estado', 'crm_disponible', 'crm_cot_abiertas', 'crm_cot_vencidas', 'crm_etapa',
        'crm_dias_sin_contacto', 'crm_hist_30', 'crm_hist_90', 'y30', 'y60', 'version']


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'\b(s ?a ?s|s ?r ?l|s ?a|ltda|limitada|sapem)\b', ' ', re.sub(r'[^a-z0-9 ]', ' ', s))
    return re.sub(r'\s+', ' ', s).strip()


def dig(s):
    return re.sub(r'\D', '', str(s or ''))


def eventos(fechas):
    ev = []
    for d in sorted(set(fechas)):
        if not ev or (d - ev[-1]).days >= AGRUPAR:
            ev.append(d)
    return ev


def fila_compras(cs, corte):
    """cs: [(fecha, tipo, cantidad, producto)] con fecha <= corte (el llamador filtra). Devuelve dict de rasgos."""
    ev = eventos([c[0] for c in cs])
    inter = [(b - a).days for a, b in zip(ev, ev[1:])]
    ciclo = statistics.median(inter) if len(inter) >= 2 else None
    mad = statistics.median(abs(x - ciclo) for x in inter) if ciclo else None
    dias_ult = (corte - ev[-1]).days
    u365 = [c for c in cs if (corte - c[0]).days <= 365]
    tot = sum(c[2] for c in u365) or 1.0
    part = lambda t: round(sum(c[2] for c in u365 if c[1] == t) / tot, 4)
    n = lambda dd: sum(1 for e in ev if (corte - e).days <= dd)
    return dict(dias_ult=dias_ult, ev_90=n(90), ev_180=n(180), ev_365=n(365), ev_tot=len(ev),
                unid_365=sum(c[2] for c in u365), ciclo=ciclo, mad=mad,
                ratio_ciclo=round(dias_ult / ciclo, 4) if ciclo else None,
                dist_prox=(dias_ult - ciclo) if ciclo else None, part_onu=part('onu'), part_cable=part('cable'),
                part_inv=part('inv'), antig=(corte - ev[0]).days, skus_365=len({c[3] for c in u365}))


def fila_pedidos(ps, corte):
    """ps: [(fecha_pedido, fecha_factura o None)]. Abierto = cargado <= corte y sin factura <= corte."""
    vis = [p for p in ps if p[0] <= corte]
    abiertos = sum(1 for p in vis if p[1] is None or p[1] > corte)
    return dict(ped_abiertos=abiertos, dias_ult_pedido=(corte - max(p[0] for p in vis)).days if vis else None)


def objetivo(cs_todas, corte, dias, ultimo):
    if corte + D.timedelta(days=dias) > ultimo:
        return None
    return int(any(corte < c[0] <= corte + D.timedelta(days=dias) for c in cs_todas))


def tipo(txt):
    return 'onu' if ONU.search(txt) else 'inv' if INVERSION.search(txt) else 'cable' if CABLE.search(txt) else 'otro'


def leer(db):
    q = lambda s: db.run([(s, [])])[0][1]
    compras = {}
    for cuit, f, prod, sub, fam, cant in q('SELECT cuit, fecha, producto, subfamilia, familia, cantidad_neta FROM limpia_compras_firmes '
                                           'WHERE coalesce(otro_vendedor,0)=0 AND cantidad_neta > 0 AND cuit IS NOT NULL'):
        compras.setdefault(cuit, []).append((D.date.fromisoformat(f[:10]), tipo(' '.join(str(x or '') for x in (prod, sub, fam))),
                                             float(cant or 0), prod))
    nombre_cuit = {}
    for cuit, cli in q('SELECT DISTINCT cuit, cliente FROM limpia_comprobantes WHERE cuit IS NOT NULL'):
        nombre_cuit.setdefault(norm(cli), cuit)
    fecha_tid = {t: f for t, f in q('SELECT tid, fecha FROM limpia_comprobantes')}
    pedidos = {}
    for fecha, cli, ftid in q('SELECT fecha, cliente, factura_tid FROM limpia_pedidos'):
        cuit = nombre_cuit.get(norm(cli))
        if cuit and fecha:
            ff = fecha_tid.get(ftid)
            pedidos.setdefault(cuit, []).append((D.date.fromisoformat(fecha[:10]), D.date.fromisoformat(ff[:10]) if ff else None))
    cue = {}
    for cuit, trabajar, estado in q('SELECT cuit, trabajar, estado FROM cue_cuentas WHERE cuit IS NOT NULL'):
        for c in str(cuit).replace(';', ',').split(','):
            if dig(c):
                cue[dig(c)] = (trabajar, estado)
    crm = {'oportunidades': [], 'cotizaciones': []}
    for col, i, data in q("SELECT coleccion, id, data FROM crm WHERE coleccion IN ('oportunidades','cotizaciones')"):
        d = json.loads(data or '{}'); d['id'] = i; crm[col].append(d)
    return compras, pedidos, cue, crm


def filas_crm(crm, hoy):
    """Rasgos del CRM por CUIT, solo para el corte de hoy."""
    ops_cuit, out = {}, {}
    for o in crm['oportunidades']:
        if dig(o.get('cuit')):
            ops_cuit.setdefault(dig(o['cuit']), []).append(o)
    for cuit, ops in ops_cuit.items():
        ids = {o['id'] for o in ops}
        cots = [c for c in crm['cotizaciones'] if c.get('oportunidadId') in ids and not c.get('archivada')
                and str(c.get('estado') or '') in ABIERTAS]
        hist = [h for o in ops for h in (o.get('historial') or []) if isinstance(h, dict) and h.get('t')]
        dh = lambda h: (hoy - D.date.fromisoformat(h['t'][:10])).days
        contactos = [D.date.fromisoformat(o['ultimoContacto'][:10]) for o in ops if str(o.get('ultimoContacto') or '')[:4].isdigit()]
        etapas = [o.get('etapa') for o in ops if o.get('etapa')]
        out[cuit] = dict(crm_cot_abiertas=len(cots), crm_cot_vencidas=sum(1 for c in cots if str(c.get('vence') or '9') < hoy.isoformat()),
                         crm_etapa=etapas[0] if len(set(etapas)) == 1 else ('varias' if etapas else None),
                         crm_dias_sin_contacto=(hoy - max(contactos)).days if contactos else None,
                         crm_hist_30=sum(1 for h in hist if 0 <= dh(h) <= 30), crm_hist_90=sum(1 for h in hist if 0 <= dh(h) <= 90))
    return out


def armar(compras, pedidos, cue, crm, hoy):
    ultimo = max(c[0] for cs in compras.values() for c in cs)
    cortes, c = [], INICIO
    while c < hoy:
        cortes.append(c); c += D.timedelta(days=PASO)
    cortes.append(hoy)
    rcrm = filas_crm(crm, hoy)
    filas, fugas = [], []
    for corte in cortes:
        for cuit, cs in compras.items():
            vis = [x for x in cs if x[0] <= corte]
            if not vis:
                continue
            ps = pedidos.get(cuit, [])
            # control de fugas: nada de lo usado puede ser posterior al corte
            if any(x[0] > corte for x in vis):
                fugas.append((corte, cuit))
            f = dict(corte=corte.isoformat(), cuit=cuit, **fila_compras(vis, corte), **fila_pedidos(ps, corte))
            t, e = cue.get(dig(cuit), (None, None))
            f.update(cue_trabajar=t, cue_estado=e, crm_disponible=int(corte == hoy))
            vacio = dict(crm_cot_abiertas=None, crm_cot_vencidas=None, crm_etapa=None, crm_dias_sin_contacto=None, crm_hist_30=None, crm_hist_90=None)
            f.update(rcrm.get(dig(cuit), dict(vacio, crm_cot_abiertas=0, crm_cot_vencidas=0, crm_hist_30=0, crm_hist_90=0)) if corte == hoy else vacio)
            f.update(y30=objetivo(cs, corte, 30, ultimo), y60=objetivo(cs, corte, 60, ultimo), version=VERSION)
            if f['dias_ult'] < 0 or (f['dias_ult_pedido'] is not None and f['dias_ult_pedido'] < 0):
                fugas.append((corte, cuit))
            filas.append(f)
    return filas, fugas, ultimo


def escribir(db, filas, fugas, ultimo, hoy):
    ahora = D.datetime.now(D.timezone.utc).isoformat(timespec='seconds')
    ctl = [('CREATE TABLE IF NOT EXISTS red_control(calculado, version, corte_hoy, ultimo_dato, filas, fugas, estado, detalle)', []),
           ('INSERT INTO red_control VALUES(?,?,?,?,?,?,?,?)', [ahora, VERSION, hoy.isoformat(), ultimo.isoformat(), len(filas), len(fugas),
                                                              'FALLA' if fugas else 'PASA', json.dumps([list(map(str, x)) for x in fugas[:20]])])]
    if fugas:
        db.run(ctl)
        return 'FALLA'
    lote = [('DROP TABLE IF EXISTS red_rasgos', []), ('CREATE TABLE red_rasgos(' + ', '.join(COLS) + ')', [])]
    lote += [('INSERT INTO red_rasgos VALUES(' + ','.join('?' * len(COLS)) + ')', [f[c] for c in COLS]) for f in filas]
    for i in range(0, len(lote), 500):
        db.run(lote[i:i + 500])
    db.run(ctl)
    return 'PASA'


def autotest():
    d = D.date.fromisoformat
    cs = [(d('2026-01-01'), 'onu', 100, 'A'), (d('2026-01-05'), 'onu', 20, 'A'), (d('2026-02-01'), 'onu', 50, 'A'),
          (d('2026-03-03'), 'cable', 10, 'B'), (d('2026-04-02'), 'onu', 30, 'A')]
    corte = d('2026-03-10')
    f = fila_compras([c for c in cs if c[0] <= corte], corte)
    p = fila_pedidos([(d('2026-03-01'), d('2026-03-20')), (d('2026-02-01'), d('2026-02-03')), (d('2026-03-15'), None)], corte)
    casos = [
        ('entrega a menos de 15 días = un evento', f['ev_tot'] == 3),
        ('ciclo = mediana de intervalos (31, 30)', f['ciclo'] == 30.5 and f['dias_ult'] == 7),
        ('no mira compras posteriores al corte', f['unid_365'] == 180 and f['skus_365'] == 2),
        ('pedido abierto al corte aunque se facture después', p['ped_abiertos'] == 1 and p['dias_ult_pedido'] == 9),
        ('pedido cargado después del corte no cuenta', p['ped_abiertos'] == 1),
        ('objetivo y30: compró el 02/04 (dentro de 30 días)', objetivo(cs, corte, 30, d('2026-11-20')) == 1),
        ('objetivo sin ventana completa = NULL', objetivo(cs, d('2026-11-01'), 30, d('2026-11-20')) is None),
    ]
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    ok = sum(x for _, x in casos)
    print(f'autotest red_rasgos: {ok}/{len(casos)}')
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
        hoy = D.date.fromisoformat(a[a.index('--hoy') + 1]) if '--hoy' in a else D.datetime.now(D.timezone(D.timedelta(hours=-3))).date()
        db = loki(os.path.join(AQUI, '..', 'loki', 'loki_sql.py')).conectar()
        filas, fugas, ultimo = armar(*leer(db), hoy)
        est = escribir(db, filas, fugas, ultimo, hoy)
        db.close()
        print('RESUMEN ' + json.dumps(dict(estado=est, filas=len(filas), fugas=len(fugas), clientes=len({f['cuit'] for f in filas}),
                                           cortes=len({f['corte'] for f in filas}), con_y30=sum(f['y30'] is not None for f in filas),
                                           crm_hoy=sum(1 for f in filas if f['crm_disponible'] and f['crm_etapa'])), ensure_ascii=False))
        sys.exit(0 if est == 'PASA' else 1)
    print(__doc__)
