#!/usr/bin/env python3
"""motor.py v1.0.0 · motor de coincidencias de Loki (18/11/2026)

Toma un pedido en texto libre ("20 onus wifi 5", "botellas de 48", "4 km de drop", "1114")
y lo cruza con lo que vende Horizon, todo desde la base SQL de Loki:
  · catálogo con precio = lista del CRM (precio ISP) + productos Huawei/ZTT del CRM
  · stock = R8 (Finnegans) por código, con fecha de corte
  · fichas técnicas (tabla fichas) y alias propios (tabla motor_alias)
Devuelve por renglón: CUMPLE / OPCIONES / SIN PRECIO / NO TENEMOS, con precio, IVA y stock.

Uso (siempre con python3 -I; necesita loki_sql.py en la misma carpeta):
  motor.py responder "TEXTO"  |  motor.py responder -f pedido.txt     pedido completo (un renglón por línea o ';')
  motor.py buscar "TEXTO"                                               un producto suelto, top 5 con puntaje
  motor.py alias                                                        lista los alias cargados
  motor.py alias "PALABRA" "ID_LISTA" --si                              suma un alias (escribe en la base: con hacelo)
  motor.py --autotest                                                   pruebas sin red
Reglas: precio ISP de la lista (D09) · sin precio = "a confirmar" · stock "sujeto a confirmación con JP" (D05) ·
montos con IVA · Huawei: 4 % contado/transferencia · nada se inventa: lo que no está en la base se marca.
"""
import importlib.util
import json
import os
import re
import sys
import unicodedata

VERSION = '1.0.0'

# ---------------------------------------------------------------- normalización

def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', s).strip()


def compacto(s):
    return re.sub(r'[^a-z0-9]', '', norm(s))


# ---------------------------------------------------------------- conceptos
# (nombre, regex sobre el PEDIDO, regex sobre el PRODUCTO = nombre + categoría + subfamilia)
CONCEPTOS = [
    ('empalme', r'botell|domo|empalme|mufa|cierre de empalme|\bceo\b', r'empalme'),
    ('nap', r'\bnap\b|caja terminal|caja de distrib|\bcto\b|caja de abonad|caja nap|terminal optic', r'\bnap\b|terminal|fitdp-4[1-4]'),
    ('hub', r'\bhub\b', r'\bhub\b'),
    ('cable', r'cable|fibra|adss|troncal|\bfo\b|figura ?8|metros? de|\bkm\b', r'cables de fibra|fibra adss|cable optico|cable adss'),
    ('drop', r'drop|acometida', r'drop'),
    ('ont', r'\bon[ut]s?\b|modem|\bcpe\b|equipo de abonado|terminal de abonado', r'\bon[ut]\b|ont / onu'),
    ('wifi', r'wi-?fi|wireless|inalambric|\bac\b|\bax\b|dual ?band', r'onu wifi|\bx6\b|x6-'),
    ('datos', r'sin wi-?fi|solo datos|bridge|\bsfu\b', r'onu datos'),
    ('catv', r'catv|\brf\b|video|television', r'catv'),
    ('router', r'router|mesh|repetidor', r'router'),
    ('olt', r'\bolt|cabecera|chasis|chassis', r'\bolt\b|ma5800|an6000|cabecera'),
    ('placa', r'placa|tarjeta|board|puertos? pon|placa pon', r'placa|\bpcb\b'),
    ('xgs', r'xgs|10 ?g ?pon|xg-?pon', r'xgs'),
    ('sfp', r'sfp|transceiver|modulo optic|qsfp|xfp|gbic|\bsfp\+', r'opticos y transceivers|transceiver|\bts-'),
    ('patchcord', r'patch ?cord|jumper|cordon', r'patchcord'),
    ('pigtail', r'pigtail|colita', r'pigtail'),
    ('conector', r'conector|mecanic', r'^conector'),
    ('fastconnect', r'fast ?connect|preconect', r'fastconnect|preconectorizad'),
    ('splitter', r'splitter|spliter|divisor', r'splitter'),
    ('odf', r'\bodf\b|distribuidor|bandeja|repartidor|patch ?panel|\brack\b|\blgx\b', r'distribuidor|\brack\b|\blgx\b'),
    ('roseta', r'roseta|toma optica|wall ?box', r'roseta'),
    ('switch', r'switch', r'switch'),
    ('energia', r'fuente|rectificador|energia|bateri|-?48 ?v', r'rct100|fuente|etp48|energia'),
]
CQ = [(n, re.compile(q)) for n, q, _ in CONCEPTOS]
CP = [(n, re.compile(p)) for n, _, p in CONCEPTOS]

# Conceptos que dicen QUÉ es el producto: si el pedido lo nombra y el producto no lo es, casi no compite.
TIPOS = {'empalme', 'nap', 'hub', 'drop', 'ont', 'router', 'olt', 'placa', 'sfp', 'patchcord', 'pigtail',
         'conector', 'splitter', 'odf', 'roseta', 'switch', 'energia'}

# Datos que la base no tiene escritos y vienen de Nicolás o del nombre del modelo (fuente al lado).
ATRIB = {
    'hg6543d': {'wifi5': 'Nicolás: es WiFi 5'},
    'eg8145x610': {'wifi6': 'Huawei X6 = WiFi 6'},
    'eg8041x610': {'wifi6': 'Huawei X6 = WiFi 6'},
    'eg8147x610': {'wifi6': 'Huawei X6 = WiFi 6'},
}

VAR = r'\bpkp\b|\bpk\b|c\+\+|c\+(?!\+)|\btotalmente\b|\bclick\b|\bmini\b|\bcompacto\b|\bcombo\b|\bexpansion\b'

# Palabras de pedido que no aportan nada al cruce
VACIAS = set('de del la las el los un una unos unas para con sin y o x por cada mas necesito quiero cotizar cotizame precio '
             'precios favor pasame unidades unidad u un. uds mts mt m metros metro km rollo rollos bobina bobinas tipo modelo'.split())


def conceptos_pedido(t):
    c = {n for n, r in CQ if r.search(t)}
    if re.search(r'wi-?fi ?6|\bax\d*\b|wifi6', t):
        c |= {'wifi', 'wifi6'}
    elif re.search(r'wi-?fi ?5|\bac\d*\b|wifi5', t):
        c |= {'wifi', 'wifi5'}
    if 'datos' in c:
        c.discard('wifi')
    if 'drop' in c:
        c.add('cable')
    if 'fastconnect' in c and 'conector' in c and not re.search(r'conector', t.replace('fast connect', '')):
        c.discard('conector')
    return c


def fibras(t, pedido=True):
    """Cantidad de fibras/puertos que nombra el texto (48F, 48 fibras, 48 hilos, botella de 48)."""
    m = re.search(r'(\d{1,3}) ?(?:f\b|fo\b|fibras?|hilos|pelos|puertos|bocas)', t)
    if m:
        return int(m.group(1))
    if pedido:
        m = re.search(r'(?:botell\w*|domo|empalme|caja|cable|adss|fibra|odf|distribuidor)\w* (?:de )?(\d{2,3})\b', t)
        if m and int(m.group(1)) in (2, 4, 6, 8, 12, 16, 24, 36, 48, 72, 96, 144, 288, 480):
            return int(m.group(1))
    return None


def tokens_modelo(t):
    """Tokens con letras y números (HG6543D, AN6000-7, 420A, S5735, GPOA)."""
    out = set()
    for w in re.findall(r'[a-z0-9][a-z0-9\-/+.]*', t):
        c = re.sub(r'[^a-z0-9+]', '', w)
        if len(c) >= 4 and re.search(r'\d', c) and re.search(r'[a-z]', c):
            out.add(c)
    for w in re.findall(r'\b(gpoa|gfoa|gpuf|gphf|gpsf|gpfd|flhf|cghf|hu8a|gpcmm|flgcmm|cgcbcm|flcbcm|qce|ste|rct100|lgx|easyconns)\b', t):
        out.add(w)
    return out


# ---------------------------------------------------------------- pedido

def partir_pedido(texto):
    lineas = []
    for l in re.split(r'[\n;]+|\s\+\s', texto):
        l = re.sub(r'^\s*(?:[-*•·]|\d+[.)])\s+', '', l).strip()
        if l:
            lineas.append(l)
    return lineas


def cantidad(l):
    """(cantidad, unidad, resto). Acepta '20 onus', '4 km de drop', 'x 20', '4.000 m', 'ONT x20'."""
    t = norm(l)
    m = re.match(r'^(\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?)\s*(km|mts?|metros?|m|u|uds?|unid\w*|x)?\b\.?\s*(.*)$', t)
    if not m:
        m2 = re.search(r'(?:\bx|cant\w*:?)\s*(\d{1,3}(?:\.\d{3})+|\d+)\s*(km|mts?|metros?|m|u)?\b', t)
        if not m2:
            return None, None, t
        n, u, resto = m2.group(1), m2.group(2), (t[:m2.start()] + ' ' + t[m2.end():]).strip()
    else:
        n, u, resto = m.group(1), m.group(2), m.group(3)
        if re.fullmatch(r'\d{3,4}', n) and not u and not resto:
            return None, None, t           # renglón que es solo un código
    q = float(n.replace('.', '').replace(',', '.'))
    if u == 'km':
        q, u = q * 1000, 'm'
    elif u and u.startswith('m'):
        u = 'm'
    elif u in (None, 'x'):
        u = None
    else:
        u = 'u'
    return q, u, resto


# ---------------------------------------------------------------- catálogo

def _cargar_loki_sql():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'loki_sql.py')
    spec = importlib.util.spec_from_file_location('loki_sql', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def catalogo(db, q):
    items = []
    for r in q(db, "SELECT id, data FROM crm WHERE coleccion='lista'"):
        d = json.loads(r['data'])
        items.append({'id': r['id'], 'nombre': d.get('nombre', ''), 'cat': d.get('categoria', ''), 'precio': d.get('isp'),
                      'iva': d.get('iva'), 'unidad': d.get('unidad') or 'unidad', 'fuente': d.get('fuente') or 'lista CRM',
                      'act': d.get('actualizado'), 'marca': 'FiberHome' if ' FH ' in f" {d.get('nombre', '')} " else ''})
    for r in q(db, "SELECT id, data FROM crm WHERE coleccion='productos'"):
        d = json.loads(r['data'])
        hw = (d.get('marca') or '').lower() == 'huawei' or 'huawei' in d.get('nombre', '').lower()
        ztt = 'ztt' in d.get('nombre', '').lower()
        items.append({'id': r['id'], 'nombre': d.get('nombre', ''), 'cat': d.get('categoria', ''), 'precio': d.get('precio'),
                      'iva': '10.5%' if ztt else d.get('iva'), 'unidad': d.get('unidad') or ('metro' if ztt else 'unidad'),
                      'fuente': d.get('lista') or 'productos CRM', 'act': d.get('actualizado'),
                      'marca': 'Huawei' if hw else ('ZTT' if ztt else d.get('marca', '')),
                      'contado': d.get('descuentoContado')})
    # stock R8 por código
    sk = {}
    for r in q(db, 'SELECT productoid, producto, subfamilia, stock, pedidos_sf, en_transito, total FROM stock'):
        s = sk.setdefault(r['productoid'], {'cod': r['productoid'], 'nombre': (r['producto'] or '').strip(), 'sub': r['subfamilia'] or '',
                                            'stock': 0.0, 'pedidos': 0.0, 'total': None})
        s['stock'] += r['stock'] or 0
        s['pedidos'] += r['pedidos_sf'] or 0
        if r['total'] is not None:
            s['total'] = (s['total'] or 0) + r['total']
    por_nombre = {}
    for s in sk.values():
        por_nombre.setdefault(compacto(s['nombre']), []).append(s)
    for it in items:
        cands = por_nombre.get(compacto(it['nombre']), [])
        if not cands:                                     # mismo modelo dentro del nombre
            tm = tokens_modelo(norm(it['nombre']))
            cands = [s for s in sk.values() if tm and tm & tokens_modelo(norm(s['nombre']))
                     and compacto(it['cat'])[:3] != 'cab']  # evita cruces de cables por "as80"
            if len(cands) > 2:
                cands = []
        it['stock'] = cands
        it['sub'] = ' '.join({s['sub'] for s in cands})
    corte = {r['fuente']: str(r['corte'])[:10] for r in q(db, "SELECT fuente, corte FROM cargas WHERE fuente IN ('R8','R10','crm:lista','crm:productos')")}
    try:
        alias = q(db, 'SELECT alias, producto FROM motor_alias')
    except Exception:
        alias = []
    return preparar(items, list(sk.values()), alias), corte


def preparar(items, stock, alias):
    al = {}
    for a in alias:
        al.setdefault(a['producto'], []).append(norm(a['alias']))
    for it in items:
        cat_t = norm(it['cat']).replace('cajas, nap y distribucion', 'distribucion optica').replace('conectores y patchcords', 'conectividad')
        texto = norm(f"{it['nombre']} {cat_t} {it.get('sub', '')}")
        it['_t'] = texto
        it['_c'] = {n for n, r in CP if r.search(texto)}
        if 'cable' in it['_c'] and 'drop' not in it['_c'] and re.search(r'cfoa|as80|as120|adss', texto):
            it['_c'].add('adss')
        it['_f'] = fibras(norm(it['nombre']), pedido=False) or (lambda m: int(m.group(1)) if m else None)(
            re.search(r'(\d{2,3}) (?:fibras|puertos)', norm(it['nombre'])))
        it['_m'] = tokens_modelo(norm(it['nombre']))
        it['_a'] = al.get(it['id'], [])
        it['_attr'] = ATRIB.get(compacto(it['nombre']).replace('ontgpon', '').replace('ont', '', 1), {})
        for k in it['_attr']:
            it['_c'].add(k)
            it['_c'].add('wifi')
    return {'items': items, 'stock': stock}


# ---------------------------------------------------------------- cruce

def puntuar(it, t, qc, qf, qm):
    s, notas = 0.0, []
    for a in it['_a']:
        if a and a in t:
            s += 60
            notas.append(f'alias «{a}»')
    if qm:
        hit = {m for m in qm for pm in it['_m'] if m == pm or (len(m) >= 4 and (m in pm or pm in m))}
        if hit:
            s += 70 + 10 * len(hit)
        elif any(re.search(r'\d{3}', m) for m in qm) and not it['_a']:
            s -= 15                                     # pidió un modelo y este no es
    comunes = qc & it['_c']
    faltan = {c for c in qc - it['_c'] if c not in ('wifi5', 'wifi6', 'cable')}
    s += 12 * len(comunes) - sum(25 if c in TIPOS else 9 for c in faltan)
    if 'cable' in qc and 'cable' not in it['_c'] and not (qc & {'patchcord', 'pigtail', 'fastconnect'}):
        s -= 9
    for g in ('wifi5', 'wifi6'):
        if g in qc and g not in it['_c'] and 'ont' in it['_c']:
            otra = 'wifi6' if g == 'wifi5' else 'wifi5'
            if otra in it['_c']:
                s -= 25
            else:
                notas.append(f'WiFi {g[-1]}: sin dato en la base, confirmar con la ficha')
    if qf:
        if it['_f'] == qf:
            s += 18
        elif it['_f'] and (qc & {'empalme', 'cable', 'odf', 'nap', 'adss'}):
            s -= 30 if it['_f'] < qf else 12           # más chico no cumple; más grande cumple pero sobra
            if it['_f'] > qf:
                notas.append(f'pidió {qf}F, esta es de {it["_f"]}F')
    qr = re.search(r'\b1 ?x ?(\d{1,2})\b', t)
    if qr:
        pr = re.search(r'\b1 ?x ?(\d{1,2})\b', it['_t'])
        if pr and pr.group(1) == qr.group(1):
            s += 20
        elif pr or 'splitter' in it['_c']:
            s -= 30
    # variantes que separan productos casi iguales (PK/PKP, C+/C++, Seco/Totalmente Seco, Click, Mini, Compacto)
    qv = set(re.findall(VAR, t))
    pv = set(re.findall(VAR, it['_t']))
    s += 6 * len(qv & pv) - 6 * len(pv - qv) - 4 * len(qv - pv)
    pal = {w for w in re.findall(r'[a-z0-9]{4,}|\b[au]pc\b|\blc\b|\bsc\b|\bfc\b', t) if w not in VACIAS}
    s += 2 * len({w for w in pal if w in it['_t']})
    return s, notas


def cruzar(cat, linea):
    q_, u, resto = cantidad(linea)
    t = norm(resto)
    res = {'linea': linea, 'cant': q_, 'unidad': u, 'estado': 'NO TENEMOS', 'item': None, 'opciones': [], 'notas': [], 'sinprecio': []}
    # código de Finnegans (3-4 dígitos solos)
    codigos = re.findall(r'(?<![\w.,/-])(\d{3,4})(?![\w.,/-])', t)
    for c in codigos:
        if not re.search(r'(\d{3,4}) ?(?:f\b|fibras|puertos|m\b|mts|metros)', t):
            for it in cat['items']:
                if any(s['cod'] == c for s in it['stock']):
                    res.update(estado='CUMPLE', item=it)
                    res['notas'].append(f'código {c}')
                    return res
            s = next((s for s in cat['stock'] if s['cod'] == c), None)
            if s:
                res.update(estado='SIN PRECIO', sinprecio=[s])
                res['notas'].append(f'código {c} está en Finnegans pero no en la lista de precios: precio a confirmar')
                return res
    exacto = [it for it in cat['items'] if compacto(it['nombre']) == compacto(t)]
    if len(exacto) == 1:
        res.update(estado='CUMPLE', item=exacto[0])
        return res
    qc, qf, qm = conceptos_pedido(t), fibras(t), tokens_modelo(t)
    if not (qc or qm or any(a and a in t for it in cat['items'] for a in it['_a'])):
        res['notas'].append('no entendí qué producto es: decime la palabra y la sumo como alias')
        return res
    pts = sorted(((puntuar(it, t, qc, qf, qm), it) for it in cat['items']),
                 key=lambda x: (-x[0][0], -sum(s_['stock'] for s_ in x[1]['stock'])))
    pts = [p for p in pts if p[0][0] >= 10]
    if pts:
        top = pts[0][0][0]
        cerca = [p for p in pts if p[0][0] >= top - 6][:6]
        # un solo producto con distinto largo/variante no es ambigüedad si el pedido nombró el modelo exacto
        if len(cerca) == 1 or (qm and top >= 80 and (len(cerca) == 1 or cerca[1][0][0] < top - 1)):
            res.update(estado='CUMPLE', item=cerca[0][1])
            res['notas'] += cerca[0][0][1]
        else:
            res.update(estado='OPCIONES', opciones=[(p[1], p[0][1]) for p in cerca])
    # productos de Finnegans sin precio de lista que coinciden por modelo
    if res['estado'] in ('NO TENEMOS', 'OPCIONES'):
        en_lista = {s['cod'] for it in cat['items'] for s in it['stock']}
        qr = re.search(r'\b1 ?x ?(\d{1,2})\b', t)
        def sirve(s):
            n = norm(s['nombre'] + ' ' + s['sub'])
            if qm:
                return bool(qm & tokens_modelo(n))
            if qr:
                return bool({c for c, r in CP if r.search(n)} & qc) and re.search(r'\b1 ?x ?' + qr.group(1) + r'\b', n) is not None
            return False
        sp = sorted((s for s in cat['stock'] if s['cod'] not in en_lista and sirve(s)), key=lambda s: -s['stock'])
        if sp:
            res['sinprecio'] = sp[:3]
            if res['estado'] == 'NO TENEMOS':
                res['estado'] = 'SIN PRECIO'
    return res


# ---------------------------------------------------------------- salida

def iva_n(iva):
    try:
        return float(str(iva).replace('%', '').replace(',', '.')) / 100
    except (TypeError, ValueError):
        return None


def stock_txt(it_o_s):
    ss = it_o_s.get('stock') if 'precio' in it_o_s else [it_o_s]
    if not ss:
        return 'stock: sin código en R8'
    fis = sum(s['stock'] for s in ss)
    ped = sum(s['pedidos'] for s in ss)
    tot = sum(s['total'] for s in ss if s['total'] is not None) if any(s['total'] is not None for s in ss) else None
    cod = '/'.join(sorted({s['cod'] for s in ss}))
    t = f'cód. {cod} · stock {fis:,.0f}'.replace(',', '.')
    if ped:
        t += f' (comprometido {ped:,.0f})'.replace(',', '.')
    if tot is not None and tot != fis - ped:
        t += f' · total con producción/tránsito {tot:,.0f}'.replace(',', '.')
    return t


def renglon_precio(it, cant):
    p, iv = it.get('precio'), iva_n(it.get('iva'))
    if p is None:
        return 'precio a confirmar', None
    u = 'm' if (it.get('unidad') or '').startswith('met') else 'u'
    t = f"USD {p:g}/{u} + IVA {it.get('iva') or 'a confirmar'}"
    tot = None
    if cant:
        neto = p * cant
        if iv is not None:
            tot = neto * (1 + iv)
            t += f' · {cant:g} {u} = neto {neto:,.2f} · c/IVA {tot:,.2f}'
        else:
            t += f' · {cant:g} {u} = neto {neto:,.2f} (IVA a confirmar)'
    if it.get('contado'):
        t += f" · {it['contado']} % menos contado/transferencia"
    return t, tot


def responder(cat, corte, texto, solo=False):
    out, total, revisar = [], 0.0, []
    lineas = [texto] if solo else partir_pedido(texto)
    for i, l in enumerate(lineas, 1):
        r = cruzar(cat, l)
        out.append(f'{i}. «{l}» → {r["estado"]}')
        if r['item']:
            it = r['item']
            pt, tot = renglon_precio(it, r['cant'])
            total += tot or 0
            out.append(f"   {it['nombre']} · {pt}")
            out.append(f"   {stock_txt(it)} · precio: {it['fuente']}")
            if r['cant'] is None:
                revisar.append(f'{i}: falta la cantidad')
        for it, notas in r['opciones']:
            pt, _ = renglon_precio(it, r['cant'])
            out.append(f"   ? {it['nombre']} · {pt} · {stock_txt(it)}" + (f" · {'; '.join(notas)}" if notas else ''))
        if r['opciones']:
            revisar.append(f'{i}: elegir entre {len(r["opciones"])} opciones')
        for s in r['sinprecio']:
            out.append(f"   · {s['nombre']} · {stock_txt(s)} · NO está en la lista: precio a confirmar")
        for n in r['notas']:
            out.append(f'   ojo: {n}')
            if 'confirmar' in n:
                revisar.append(f'{i}: {n}')
        if r['estado'] == 'NO TENEMOS':
            revisar.append(f'{i}: no hay producto en la lista que cumpla')
    if not solo:
        out.append(f'\nTOTAL c/IVA de lo que CUMPLE: USD {total:,.2f}' if total else '\nTOTAL: sin renglones con precio y cantidad')
        if revisar:
            out.append('REVISAR antes de enviar: ' + ' · '.join(revisar))
    out.append(f"Fuentes: lista CRM {corte.get('crm:lista', '?')} · stock R8 {corte.get('R8', '?')} (sujeto a confirmación con JP) · "
               f'precios especiales del cliente: no están en la base · motor.py {VERSION}')
    return '\n'.join(out)


def buscar(cat, corte, texto):
    t = norm(texto)
    qc, qf, qm = conceptos_pedido(t), fibras(t), tokens_modelo(t)
    pts = sorted(((puntuar(it, t, qc, qf, qm), it) for it in cat['items']), key=lambda x: -x[0][0])[:5]
    out = [f'«{texto}» · conceptos {sorted(qc) or "-"} · fibras {qf or "-"} · modelo {sorted(qm) or "-"}']
    for (s, notas), it in pts:
        pt, _ = renglon_precio(it, None)
        out.append(f'  {s:5.0f}  {it["nombre"]} · {pt} · {stock_txt(it)}' + (f" · {'; '.join(notas)}" if notas else ''))
    out.append(f"Fuentes: lista CRM {corte.get('crm:lista', '?')} · R8 {corte.get('R8', '?')}")
    return '\n'.join(out)


# ---------------------------------------------------------------- autotest (sin red)

def autotest():
    items = [
        {'id': 'hg6543d', 'nombre': 'Ont Gpon HG6543D', 'cat': 'ONT / ONU', 'precio': 25.5, 'iva': '10.5%', 'unidad': 'unidad', 'fuente': 'L',
         'stock': [{'cod': '1114', 'nombre': 'Ont Gpon HG6543D', 'sub': 'ONU WIFI TELEF DB', 'stock': 898, 'pedidos': 41, 'total': 857}],
         'sub': 'ONU WIFI TELEF DB'},
        {'id': 'hg6145f3', 'nombre': 'Ont Gpon HG6145F3', 'cat': 'ONT / ONU', 'precio': 38, 'iva': '10.5%', 'unidad': 'unidad', 'fuente': 'L',
         'stock': [], 'sub': 'ONU WIFI TELEF DB'},
        {'id': 'eg8145', 'nombre': 'ONT EG8145X6-10', 'cat': 'ONT / ONU', 'precio': 47.4, 'iva': '10.5%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'an5506', 'nombre': 'Ont Gpon AN5506-01ABG', 'cat': 'ONT / ONU', 'precio': 19.5, 'iva': '10.5%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': 'ONU DATOS'},
        {'id': 'ce48', 'nombre': 'Caja de empalme optico FH 48 fibras CM', 'cat': 'Cajas, NAP y distribución', 'precio': 51.55, 'iva': '21%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'ce144', 'nombre': 'Caja de empalme optico FH 144 fibras CM', 'cat': 'Cajas, NAP y distribución', 'precio': 67.95, 'iva': '21%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'drop', 'nombre': 'Cable Óptico Drop Compacto FH Acero 1F', 'cat': 'Cables de fibra', 'precio': 0.1181, 'iva': '10.5%', 'unidad': 'metro', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'as80-48', 'nombre': 'Cable Óptico FH CFOA-SM-AS80-S 48F PK', 'cat': 'Cables de fibra', 'precio': 1.59, 'iva': '10.5%', 'unidad': 'metro', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'as80-24', 'nombre': 'Cable Óptico FH CFOA-SM-AS80-S 24F PK', 'cat': 'Cables de fibra', 'precio': 0.92, 'iva': '10.5%', 'unidad': 'metro', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': '420a', 'nombre': 'Caja terminal FitDP-420A', 'cat': 'Cajas, NAP y distribución', 'precio': 60, 'iva': '21%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'gpuf', 'nombre': 'Placa Huawei GPUF C+', 'cat': 'Huawei · placas GPON', 'precio': 1039.5, 'iva': None, 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': '', 'contado': 4},
        {'id': 'sp18', 'nombre': 'Splitter optico FH 1x4 NC - SC/APC', 'cat': 'Cajas, NAP y distribución', 'precio': 4.94, 'iva': '21%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
    ]
    stock = [it['stock'][0] for it in items if it['stock']] + [{'cod': '1070', 'nombre': 'Caja de empalme optico CEO II FM DPR', 'sub': '', 'stock': 0, 'pedidos': 0, 'total': 0}]
    cat = preparar(items, stock, [{'alias': 'king box', 'producto': '420a'}])
    casos = [
        ('20 onus wifi 5', 'CUMPLE', 'hg6543d'), ('HG6543D', 'CUMPLE', 'hg6543d'), ('1114', 'CUMPLE', 'hg6543d'),
        ('10 botellas de 48', 'CUMPLE', 'ce48'), ('5 domos 144 fibras', 'CUMPLE', 'ce144'), ('4 km de drop', 'CUMPLE', 'drop'),
        ('8000 m adss 48f', 'CUMPLE', 'as80-48'), ('2 placas GPUF 16 port C+', 'CUMPLE', 'gpuf'), ('50 king box', 'CUMPLE', '420a'),
        ('100 onu wifi 6', 'CUMPLE', 'eg8145'), ('30 onu solo datos', 'CUMPLE', 'an5506'), ('1070', 'SIN PRECIO', None),
        ('3 licuadoras', 'NO TENEMOS', None), ('25 onus', 'OPCIONES', None), ('20 cajas nap', 'CUMPLE', '420a'),
    ]
    ok = 0
    for txt, est, iid in casos:
        r = cruzar(cat, txt)
        bien = r['estado'] == est and (iid is None or (r['item'] or {}).get('id') == iid)
        ok += bien
        print(('PASA ' if bien else 'FALLA'), txt, '→', r['estado'], (r['item'] or {}).get('id'))
    q_, u, _ = cantidad('4 km de drop')
    ok2 = q_ == 4000 and u == 'm'
    print(('PASA ' if ok2 else 'FALLA'), 'cantidad 4 km = 4000 m')
    q_, u, _ = cantidad('4.000 m de adss')
    ok3 = q_ == 4000
    print(('PASA ' if ok3 else 'FALLA'), 'cantidad 4.000 m')
    n = len(casos) + 2
    tot = ok + ok2 + ok3
    print(f'autotest motor.py {VERSION}: {tot}/{n}')
    return 0 if tot == n else 1


# ---------------------------------------------------------------- main

def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    if a[0] == '--autotest':
        return autotest()
    ls = _cargar_loki_sql()
    db = ls.conectar()
    try:
        if a[0] == 'alias':
            if len(a) == 1:
                try:
                    rs = ls.q(db, 'SELECT alias, producto, fuente FROM motor_alias ORDER BY producto')
                except Exception:
                    rs = []
                print('\n'.join(f"{r['alias']} → {r['producto']} ({r['fuente']})" for r in rs) or 'sin alias cargados')
                return 0
            if '--si' not in a:
                print('Sumar un alias escribe en la base: hace falta el hacelo de Nicolás (repetir con --si).')
                return 1
            pal, pid = a[1], a[2]
            db.run([('CREATE TABLE IF NOT EXISTS motor_alias (alias TEXT NOT NULL, producto TEXT NOT NULL, fuente TEXT, '
                     'creado TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (alias, producto))', []),
                    ('INSERT OR REPLACE INTO motor_alias (alias, producto, fuente) VALUES (?, ?, ?)', [norm(pal), pid, 'Nicolás (chat)'])])
            print(f'OK alias «{norm(pal)}» → {pid}')
            return 0
        cat, corte = catalogo(db, ls.q)
        if a[0] == 'responder':
            texto = open(a[2], encoding='utf-8').read() if len(a) > 2 and a[1] == '-f' else ' '.join(a[1:])
            print(responder(cat, corte, texto))
        elif a[0] == 'buscar':
            print(buscar(cat, corte, ' '.join(a[1:])))
        else:
            print(__doc__)
            return 1
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
