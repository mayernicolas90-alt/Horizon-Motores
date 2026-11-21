#!/usr/bin/env python3
"""Loki · motor de apertura, control de datos, bitacora y verificacion de cierre (Horizon). v3.1

v3.1 (21/11): urgentes = solo venta (cierre, cotización, lead). Las entregas abiertas salen aparte en "posventa"
  (pestaña Posventa) y ya no ocupan lugares del top 5 ni de cortas (regla N01).

Uso (correr siempre con python3 -I, desde otra carpeta que los datos):
  loki.py abrir DIR [AAAA-MM-DD]        DIR con los archivos ya bajados (ver ARCHIVOS)
  loki.py buscar DIR_BITACORA TERMINO   busca en los JSON de la coleccion bitacora
  loki.py verificar MANDADO GRABADO     compara el cierre mandado contra lo grabado

No escribe en ningun lado: solo lee archivos y calcula.
"""
import csv, datetime as D, json, os, re, sys, unicodedata
from collections import Counter, defaultdict

ARCHIVOS = dict(continuidad='continuidad.json', respaldo='respaldo.json', respaldo_meta='respaldo_meta.json',
                r10='R10.csv', r10_meta='R10_meta.json', recompra='recompra.json', recompra_meta='recompra_meta.json')
COLS_R10 = ['Fecha', 'Comprobante', 'Cliente', 'Producto', 'Marca', 'Cantidad', 'Pte Dest.', 'Empresa']
FUERA = r'pogliotti|asociacion mutual mercantil|ammaa?\b|itsa\b|obercom|wiltel|gigared|generacion wi ?fi|astesano|itc comunicaciones|ax internet|fibrazo|tv music|support internet|itelsa|itel s ?a|comworks'
OTRO = r'\bsion\b|fesacom|super ?canal|comtec'
ABIERTAS = ('enviada', 'espera_aprobacion')


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    s = re.sub(r'\b(s ?a ?s|s ?r ?l|s ?a|ltda|limitada|sapem|cv|srl|sa)\b', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def fecha(s):
    try:
        return D.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def dm(s):
    d = fecha(s)
    return d.strftime('%d/%m') if d else ''


def num(s):
    try:
        return float(str(s).replace(',', '.'))
    except ValueError:
        return 0.0


def habiles(desde, n):
    d = desde
    while n:
        d += D.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def excluida(nombre):
    n = norm(nombre)
    return bool(re.search(FUERA, n) or re.search(OTRO, n))


def lista(col):
    if isinstance(col, dict):
        return [dict(v, id=v.get('id', k)) if isinstance(v, dict) else v for k, v in col.items()]
    return list(col or [])


def cargar(d):
    faltan = [f for f in ARCHIVOS.values() if not os.path.exists(os.path.join(d, f))]
    if faltan:
        sys.exit('FALTAN ARCHIVOS: ' + ', '.join(faltan))
    j = lambda k: json.load(open(os.path.join(d, ARCHIVOS[k]), encoding='utf-8'))
    with open(os.path.join(d, ARCHIVOS['r10']), encoding='utf-8', newline='') as f:
        filas = list(csv.DictReader(f, delimiter=';'))
    return {k: j(k) for k in ARCHIVOS if k != 'r10'}, filas


def seguimientos(cots, ops, hoy):
    lim = habiles(hoy, 2)
    espera = {o.get('id') for o in ops if o.get('enEspera') == 'si' and (fecha(o.get('proximaFecha')) or hoy) > hoy}
    res = []
    for c in cots:
        if c.get('estado') not in ABIERTAS or c.get('archivada') or excluida(c.get('cliente')):
            continue
        if c.get('oportunidadId') in espera:
            continue
        rev, vence = fecha(c.get('revisionFecha')), fecha(c.get('vence'))
        if rev is None:
            if not vence or vence >= hoy:
                continue
            est = 'sin_fecha'
        elif rev < hoy:
            est = 'vencido'
        elif rev == hoy:
            est = 'hoy'
        elif rev <= lim:
            est = 'proximo'
        else:
            continue
        res.append(dict(n=c.get('numero'), cliente=c.get('cliente'), est=est, rev=dm(rev), vence=dm(vence),
                        vig_vencida=bool(vence and vence < hoy)))
    orden = dict(vencido=0, hoy=1, sin_fecha=2, proximo=3)
    return sorted(res, key=lambda x: (orden[x['est']], str(x['rev'])[3:], str(x['rev'])))


def clave_comp(s):
    return re.sub(r'\D', '', str(s or ''))


def posventa(cots, filas):
    pte = defaultdict(float)
    for r in filas:
        pte[clave_comp(r.get('Comprobante'))] += num(r.get('Pte Dest.'))
    res = []
    for c in cots:
        op = c.get('hz_operacion') or {}
        if c.get('estado') != 'aceptada' or c.get('archivada') or excluida(c.get('cliente')):
            continue
        if op.get('despacho') == 'pendiente' or op.get('entrega') in ('pendiente', 'parcial'):
            fa = clave_comp(op.get('factura'))
            res.append(dict(n=c.get('numero'), cliente=c.get('cliente'), despacho=op.get('despacho') or '',
                            entrega=op.get('entrega') or '', factura=op.get('factura') or '',
                            pte_finnegans=round(pte[fa]) if fa and fa in pte else None))
    return res


def recompra(rec):
    ok = [x for x in rec if not excluida(x.get('cliente'))]
    conteo = Counter(x.get('estado') for x in ok)
    det = [dict(est=x['estado'], cliente=x['cliente'], sku=x['sku'], prox=dm(x.get('proxima')), cant=x.get('cant_prom'))
           for x in ok if x.get('estado') in ('Le toca', 'Atrasado')]
    return conteo.get('Le toca', 0), conteo.get('Atrasado', 0), det


def controles(a, filas, ops, cots, hoy):
    al, ok = [], []
    m = a['r10_meta']
    faltan = [c for c in COLS_R10 if c not in (filas[0] if filas else {})]
    (al.append('R10 sin columnas: ' + ', '.join(faltan)) if faltan else ok.append('R10 columnas'))
    if m.get('filas') != len(filas):
        al.append(f"R10 trae {len(filas)} filas y su registro dice {m.get('filas')}")
    else:
        ok.append(f'R10 {len(filas)} filas')
    corte = fecha(m.get('corte'))
    if corte and (hoy - corte).days > 7:
        al.append(f'R10 viejo: corte {dm(corte)}, pedir uno nuevo')
    sin_cli = sum(1 for r in filas if not (r.get('Cliente') or '').strip())
    if sin_cli:
        al.append(f'R10: {sin_cli} filas sin cliente')
    otras = sum(1 for r in filas if 'HORIZON TRADING' not in (r.get('Empresa') or '').upper())
    ok.append(f'R10 otras empresas fuera: {otras}')
    rm = a['respaldo_meta']
    col = a['respaldo'].get('collections', {})
    dif = [k for k, v in (rm.get('colecciones') or {}).items() if len(lista(col.get(k))) != v]
    (al.append('Respaldo no coincide en: ' + ', '.join(dif)) if dif else ok.append('Respaldo completo'))
    exp = fecha(rm.get('exportadoEn'))
    if exp and (hoy - exp).days > 3:
        al.append(f'Respaldo viejo: {dm(exp)}, pedir uno nuevo')
    rc = a['recompra_meta']
    if rc.get('corte') != m.get('corte'):
        al.append(f"Recompra con corte {dm(rc.get('corte'))} y R10 {dm(m.get('corte'))}: correr recompra.py")
    else:
        ok.append('Recompra y R10 mismo corte')
    imp = a['continuidad'].get('importante') or ''
    if len(imp.encode()) > 1024:
        al.append(f'importante pesa {len(imp.encode())} bytes')
    ids = {o.get('id') for o in ops}
    huerf = [c.get('numero') for c in cots if c.get('oportunidadId') and c.get('oportunidadId') not in ids
             and c.get('estado') in ABIERTAS and not c.get('archivada')]
    if huerf:
        al.append('Cotizaciones abiertas sin ficha: ' + ', '.join(map(str, huerf[:6])))
    # Cruce R10 contra fichas
    nombres = {norm(o.get('empresa')): o for o in ops}
    netos = defaultdict(float)
    for r in filas:
        if 'HORIZON TRADING' in (r.get('Empresa') or '').upper() and re.search('fiber ?home|\\bfh\\b', (r.get('Marca') or '') + ' ' + (r.get('Producto') or ''), re.I):
            netos[r.get('Cliente')] += num(r.get('Cantidad'))
    clientes = {r.get('Cliente') for r in filas if r.get('Cliente') and 'HORIZON TRADING' in (r.get('Empresa') or '').upper()}
    def tiene_ficha(c):
        n = norm(c)
        return n in nombres or any(k and len(k) > 5 and (k in n or n in k) for k in nombres)
    sin = sorted(c for c in clientes if not tiene_ficha(c) and not excluida(c))
    fh_no = sorted(o.get('empresa') for c, q in netos.items() if q > 0 and (o := nombres.get(norm(c))) and o.get('usaFH') != 'si' and not excluida(c))
    return dict(alertas=al, ok=ok,
                sin_ficha=dict(n=len(sin), de=len(clientes), ej=sin[:5]),
                compra_fh_sin_marcar=dict(n=len(fh_no), ej=fh_no[:8]))


def abrir(d, hoy):
    a, filas = cargar(d)
    col = a['respaldo'].get('collections', {})
    ops, cots = lista(col.get('oportunidades')), lista(col.get('cotizaciones'))
    seg, pos = seguimientos(cots, ops, hoy), posventa(cots, filas)
    letoca, atras, det = recompra(a['recompra'])
    salida = dict(hoy=hoy.isoformat(),
                  fuentes=dict(respaldo=dm(a['respaldo_meta'].get('exportadoEn')), finnegans=dm(a['r10_meta'].get('corte')), recompra=dm(a['recompra_meta'].get('actualizado'))),
                  numeros=dict(seguimientos=len(seg), cuentas=len({norm(x['cliente']) for x in seg}), posventa=len(pos), le_toca=letoca, atrasadas=atras),
                  vig_vencidas=sum(1 for x in seg if x['vig_vencida']),
                  seguimientos=seg, posventa=pos, recompra=det, control=controles(a, filas, ops, cots, hoy))
    print(json.dumps(salida, ensure_ascii=False, separators=(',', ':')))


def buscar(d, termino):
    t = norm(termino)
    hits = []
    for raiz, _, fs in os.walk(d):
        for f in fs:
            if f.endswith('.json'):
                x = json.load(open(os.path.join(raiz, f), encoding='utf-8'))
                if t in norm(' '.join(str(x.get(k, '')) for k in ('cuenta', 'tipo', 'texto'))):
                    hits.append(x)
    for x in sorted(hits, key=lambda y: str(y.get('fecha'))):
        print(f"{x.get('fecha')} · {x.get('cuenta') or '-'} · {x.get('tipo')} · {x.get('texto')}")
    print(f'[{len(hits)} resultados]')


def verificar(mandado, grabado):
    a, b = json.load(open(mandado, encoding='utf-8')), json.load(open(grabado, encoding='utf-8'))
    dif = [k for k in a if a[k] != b.get(k)]
    imp = len(str(b.get('importante', '')).encode())
    print('CIERRE OK' if not dif and imp <= 1024 else f'CIERRE CON DIFERENCIAS: {dif} · importante {imp} bytes')
    sys.exit(0 if not dif and imp <= 1024 else 1)


MIN_USD = 5000
AVISOS = {'full sat': 'el paquete V13 de GPT la marca NO TOCAR: confirmar antes de contactar', 'iplus': 'cuenta compartida con JP'}


def dias(a, b):
    a = fecha(a)
    return (b - a).days if a else None


def ojos(nombre):
    n = norm(nombre)
    return [t for k, t in AVISOS.items() if k in n]


def stock_de(d):
    """Stock menos comprometido por producto (R8), si está en la carpeta."""
    p = os.path.join(d, 'R8.csv')
    if not os.path.exists(p):
        return {}
    out = defaultdict(lambda: [0.0, 0.0, 0.0])
    for x in csv.DictReader(open(p, encoding='utf-8-sig', newline=''), delimiter=';'):
        z = out[norm(x['Producto'])]
        z[0] += num(x['Stock']); z[1] += num(x['Pedidos de venta s/f']) + num(x['Facturas de venta s/r']); z[2] += num(x['En tránsito'])
    return out


def urgentes(d, hoy):
    """Agenda del día con plata, días sin contacto y próximas acciones vencidas de las fichas. No escribe nada."""
    a, _ = cargar(d)
    col = a['respaldo'].get('collections', {})
    ops, cots = lista(col.get('oportunidades')), lista(col.get('cotizaciones'))
    por_id = {o.get('id'): o for o in ops}
    st = stock_de(d)
    top, cortas, conflictos, pos = [], [], [], []
    for c in cots:
        if c.get('archivada') or excluida(c.get('cliente')):
            continue
        o = por_id.get(c.get('oportunidadId')) or {}
        if o.get('noProspectar') or (o.get('enEspera') == 'si' and (fecha(o.get('proximaFecha')) or hoy) > hoy):
            continue
        total, n, cli, op = float(c.get('total') or 0), c.get('numero'), c.get('cliente'), c.get('hz_operacion') or {}
        sc = dias(o.get('ultimoContacto'), hoy)
        base = dict(cuenta=cli, ref=n, usd=round(total), dias_sin_contacto=sc, ojo=ojos(cli))
        if c.get('estado') in ABIERTAS:
            txt = ' '.join(str(x or '') for x in (c.get('notas'), o.get('notas'), o.get('proximaAccion'))).lower()
            if 'provisoria' in txt or 'no insistir' in txt or o.get('financiacionEstado') == 'sin_fondos' or 'tienen fondos' in txt:
                continue
            ve, edad = fecha(c.get('vence')), dias(c.get('fecha'), hoy)
            if ve and hoy <= ve <= hoy + D.timedelta(days=3):
                x = dict(base, b=1, tipo='cierre', por_que=f'vence el {dm(ve)}', accion='pedir orden de compra antes del vencimiento')
                falta = [f"{i.get('articulo')}: pide {int(i.get('cantidad') or 0)}, libres {int(st[norm(i.get('articulo'))][0] - st[norm(i.get('articulo'))][1])}, en tránsito {int(st[norm(i.get('articulo'))][2])}" for i in c.get('items', []) if norm(i.get('articulo')) in st and st[norm(i.get('articulo'))][0] - st[norm(i.get('articulo'))][1] < float(i.get('cantidad') or 0)]
                if falta:
                    x['ojo'] = x['ojo'] + ['stock R8 no alcanza: ' + '; '.join(falta) + '. Confirmar con JP']
                (top if total >= MIN_USD else cortas).append(x)
            elif edad is not None and edad <= 30:
                x = dict(base, b=3, tipo='cotización', por_que=f'cotizada hace {edad} días', accion='preguntar si la traba es precio o plazo', edad=edad)
                (top if total >= MIN_USD else cortas).append(x)
        elif c.get('estado') == 'aceptada':
            entregado = op.get('entrega') == 'confirmado'
            prox = fecha(o.get('proximaFecha')); acc = o.get('proximaAccion') or ''
            if entregado and re.search(r'(?i)confirmar entrega', acc) and n and str(n) in acc:
                conflictos.append(dict(cuenta=cli, ref=n, detalle=f'ficha dice "{acc[:70]}", operación marcada entregada {dm(op.get("entregaAt"))}'))
                continue
            if not entregado and (op.get('despacho') == 'pendiente' or op.get('entrega') in ('pendiente', 'parcial')):
                pago = op.get('pago') == 'confirmado'
                # N01: la entrega es de la pestaña Posventa, no compite con la venta en el top 5
                pos.append(dict(base, tipo='posventa', por_que=('pagó y no recibió' if pago else 'entrega abierta') + (f', fecha vencida hace {dias(prox, hoy)} días' if prox and prox < hoy else ''), accion=acc[:90]))
    con_cot = {c.get('oportunidadId') for c in cots if not c.get('archivada') and c.get('estado') in ABIERTAS}
    for o in ops:
        if o.get('archivada') or o.get('noProspectar') or excluida(o.get('empresa')) or o.get('id') in con_cot or o.get('etapa') == 'perdido':
            continue
        acc = o.get('proximaAccion') or ''
        if re.search(r'(?i)responderle|me interesa', acc):
            sc = dias(o.get('ultimoContacto'), hoy)
            if sc is not None and sc >= 7:
                top.append(dict(cuenta=o.get('empresa'), ref='lead', usd=0, dias_sin_contacto=sc, ojo=ojos(o.get('empresa')), b=4, tipo='lead sin responder', por_que=f'{sc} días sin respuesta', accion=acc[:90]))
    top.sort(key=lambda x: (x['b'], -x['usd'], x['cuenta']))
    leads = sorted((x for x in top if x['b'] == 4), key=lambda x: -x['dias_sin_contacto'])
    if leads and leads[0] not in top[:5] and len(top) >= 5:
        top.remove(leads[0]); top.insert(4, leads[0])  # un lugar reservado: responder un lead cuesta poco
    vencidas = [o for o in ops if not o.get('archivada') and not o.get('noProspectar') and not excluida(o.get('empresa')) and o.get('etapa') != 'perdido' and (fecha(o.get('proximaFecha')) or hoy) < hoy]
    muestras = [m for m in lista(col.get('muestras')) if m.get('estado') in ('pedida', 'enviada', 'prueba')]
    print(json.dumps(dict(hoy=hoy.isoformat(), top5=top[:5], siguen=top[5:], cortas=sorted(cortas, key=lambda x: -x['usd']), conflictos=conflictos,
                     posventa=sorted(pos, key=lambda x: (x['por_que'][:4] != 'pagó', -x['usd'])), fichas_con_accion_vencida=len(vencidas), muestras_abiertas=len(muestras)), ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    arg = sys.argv[1:]
    if len(arg) >= 2 and arg[0] == 'abrir':
        abrir(arg[1], fecha(arg[2]) if len(arg) > 2 else D.date.today())
    elif len(arg) >= 2 and arg[0] == 'urgentes':
        urgentes(arg[1], fecha(arg[2]) if len(arg) > 2 else D.date.today())
    elif len(arg) == 3 and arg[0] == 'buscar':
        buscar(arg[1], arg[2])
    elif len(arg) == 3 and arg[0] == 'verificar':
        verificar(arg[1], arg[2])
    else:
        sys.exit(__doc__)
