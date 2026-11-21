#!/usr/bin/env python3
"""motor.py v1.2.0 · motor de coincidencias de Loki (20/11/2026)

1.2.0 (20/11): stock y precio en vivo de Hive (Comb). Flujo: `motor.py codigos "TEXTO"` lista los códigos elegidos →
  Loki consulta Hive (consultar_stock + precio_producto) y guarda las respuestas en un JSON → `motor.py responder
  "TEXTO" --hive hive.json` usa el stock de Hive (snapshot, tránsito con ETA, producción) en lugar del R8 y avisa si el
  precio ISP de Hive difiere de la lista del CRM (el precio sigue siendo el de la lista: D09) o si la ETA ya venció.
1.1.0 (19/11): usa las fichas técnicas de la base (tabla fichas): WiFi 5/6 de las ONT, salidas de las NAP, tamaño de OLT,
  tipo de placa; deja afuera los discontinuados (D06) salvo que se pida el modelo; avisa cuando falta la marca de la OLT
  (D05); muestra la ficha de cada producto elegido. Corrige: placas que se tomaban por OLT (por la categoría).

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
  motor.py codigos "TEXTO"                                              códigos de lo elegido, para consultar Hive
  motor.py responder "TEXTO" --hive hive.json                           con stock/precio de Hive (ver formato abajo)
  motor.py --autotest                                                   pruebas sin red
hive.json: {"consultado": "AAAA-MM-DD", "productos": {"1115": {"stock": <respuesta consultar_stock.datos>,
  "precio": <respuesta precio_producto.datos>}}}  (se pegan tal cual las respuestas de Hive)
Reglas: precio ISP de la lista (D09) · sin precio = "a confirmar" · stock "sujeto a confirmación con JP" (D05) ·
montos con IVA · Huawei: 4 % contado/transferencia · nada se inventa: lo que no está en la base se marca.
"""
import importlib.util
import json
import os
import re
import sys
import unicodedata

VERSION = '1.2.0'

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
    ('nap', r'\bnap\b|caja terminal|caja de distrib|\bcto\b|caja de abonad|caja nap|terminal optic|cajas? (?:de )?1 ?x ?\d|cajas? (?:de )?\d+ (?:salidas|bocas|clientes)', r'\bnap\b|terminal|fitdp-4[1-4]'),
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
    ('xgs', r'xgs|10 ?g ?pon|xg-?pon', r'xgs|\bgfoa\b'),
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
    ('gpon', r'\bgpon\b', r'\bgpon\b|\bgpoa\b|\bgfoa\b'),
]
# 1.1.0: tamaño de OLT (pedido) → atributo del producto (fichas: AN6000-2 = 32 PON, -7 = 112, -15 = 240)
TAMANO = [('chica', r'olt (?:chica|chiquita|mini|compacta|pequena|de 2u)|mini ?olt|olt de 2 placas'),
          ('mediana', r'olt (?:mediana|intermedia)'), ('grande', r'olt (?:grande|de chasis grande)|chasis grande')]
TAMANO_DE = {'an60002': 'chica', 'an60007': 'mediana', 'an600015': 'grande', 'ma5800x7': 'mediana', 'ma5800x15': 'grande'}
# D06: discontinuados (familia Cisco / HFC): no se ofrecen salvo que se pida el modelo
DISCONT = r'\besr-|\bc7200\b|\bspa-|\bubr\b|\bcmts\b'
MARCA_PED = r'fiber ?home|\bfh\b|huawei|\bhw\b|\bzte\b|\bztt\b'
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
        m = re.search(r'(?:botell\w*|domo|empalme|caja|cable|adss|fibra|odf|distribuidor|nap|ctos?)\w* (?:(?:de|nap|terminal|optica|optico) )*(\d{1,3})\b(?! ?x)', t)
        if not m:
            m = re.search(r'(\d{1,2}) ?(?:salidas|clientes|abonados)', t)
        if m and int(m.group(1)) in (2, 4, 6, 8, 10, 12, 16, 24, 32, 36, 48, 72, 96, 144, 288, 480):
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
    t = re.sub(r'^(?:una?|uno)\b', '1', norm(l))
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
    try:   # 1.1.0: fichas técnicas (las que tienen patrón buscar se enganchan con la lista)
        fichas = q(db, 'SELECT modelo, buscar, specs FROM fichas WHERE buscar IS NOT NULL')
    except Exception:
        fichas = []
    return preparar(items, list(sk.values()), alias, fichas), corte


def _like(patron, texto):
    """LIKE de SQL (% y _), sin distinguir mayúsculas ni acentos."""
    rx = ''.join('.*' if c == '%' else '.' if c == '_' else re.escape(c) for c in norm(patron))
    return re.fullmatch(rx, norm(texto)) is not None


def attr_ficha(f):
    """Atributos que el motor usa, leídos de la ficha: WiFi 5/6 y salidas de splitter."""
    a = {}
    specs = json.loads(f['specs']) if isinstance(f['specs'], str) else f['specs']
    for dato, valor in specs:
        d, v = norm(dato), norm(valor)
        if d == 'wifi':
            if re.search(r'802\.11[a-z/ ]*ax|\bax\d{3,4}\b', v):
                a['wifi6'] = f"ficha {f['modelo']}: WiFi 6"
            elif re.search(r'802\.11[a-z/ ]*\bac\b', v):
                a['wifi5'] = f"ficha {f['modelo']}: WiFi 5"
        if d == 'splitter':
            m = re.search(r'(\d) de 1x(\d{1,2})', v)
            if m:
                a['salidas'] = int(m.group(1)) * int(m.group(2))
                a['splitter'] = f"{m.group(1)} splitters 1x{m.group(2)}"
    return a


def preparar(items, stock, alias, fichas=()):
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
        it['_attr'] = dict(ATRIB.get(compacto(it['nombre']).replace('ontgpon', '').replace('ont', '', 1), {}))
        nom = norm(it['nombre'])
        # 1.1.0: OLT solo si el NOMBRE lo dice (la categoría "OLT y placas" hacía pasar placas por OLT)
        if 'router' in it['_c']:
            it['_c'].discard('ont')          # el SR1041F está en la categoría ONT / ONU de la lista
        if 'olt' in it['_c'] and not re.search(r'\bolt\b|an6000|ma5800|\bchs\b', nom):
            it['_c'].discard('olt')
        it['_ficha'] = None
        for f in fichas:
            if f.get('buscar') and _like(f['buscar'], it['nombre']):
                it['_ficha'] = f['modelo']
                for k, v in attr_ficha(f).items():
                    it['_attr'].setdefault(k, v)
                break
        if 'salidas' in it['_attr'] and 'nap' in it['_c']:
            it['_f'] = it['_attr']['salidas']
            it['_t'] += f" {it['_attr']['salidas']} salidas {it['_attr'].get('splitter', '')}"
        for k in ('wifi5', 'wifi6'):
            if k in it['_attr']:
                it['_c'] |= {k, 'wifi'}
        it['_tam'] = TAMANO_DE.get(compacto(nom).replace('olt', '').replace('huawei', ''))
        it['_disc'] = re.search(DISCONT, nom) is not None
        it['_marca'] = 'FiberHome' if re.search(r'\bfh\b|fiberhome|fitdp|hg6|an5506|an6000|gpoa|gfoa|sr1041', nom) else (
            'Huawei' if re.search(r'huawei|\beg8|ma5800|flhf|cghf|etp48|netengine|\bs5735|\bs6730', nom) else (it.get('marca') or ''))
    return {'items': items, 'stock': stock}


# ---------------------------------------------------------------- cruce

def puntuar(it, t, qc, qf, qm):
    s, notas = 0.0, []
    if it.get('_disc') and not (qm and qm & it['_m']):
        return -100.0, ['discontinuado (D06)']
    qmar = re.search(r'fiber ?home|\bfh\b|huawei|\bhw\b', t)
    if qmar and it.get('_marca') in ('FiberHome', 'Huawei'):
        pide = 'Huawei' if qmar.group(0) in ('huawei', 'hw') else 'FiberHome'
        s += 15 if it['_marca'] == pide else -15
    qt = next((n for n, r in TAMANO if re.search(r, t)), None)
    if qt and it.get('_tam'):
        s += 25 if it['_tam'] == qt else -25
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
    if qr and 'nap' in qc and 'nap' in it['_c'] and 'splitter' not in qc:
        # 1.1.0: en una caja, «1x16» = 16 salidas (la FitDP-420A da 16 con 2 splitters 1x8)
        pr = re.search(r'\b1 ?x ?(\d{1,2})\b', it['_t'])
        sal = it['_attr'].get('salidas') or (int(pr.group(1)) if pr else it['_f'])
        if sal == int(qr.group(1)) or (pr and pr.group(1) == qr.group(1)):
            s += 20
        elif sal:
            s -= 30
    elif qr:
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
        cerca = [p for p in pts if p[0][0] >= top - 6][:8]
        if not re.search(MARCA_PED, t) and qc & {'ont', 'placa', 'olt'} and not qm:
            # 1.1.0: sin marca en el pedido, que aparezca la mejor opción de cada marca (D05: se elige con la OLT del cliente)
            vistas = {p[1].get('_marca') for p in cerca}
            for p in pts:
                if (p[0][0] >= top - 15 and p[1].get('_marca') and p[1]['_marca'] not in vistas and len(cerca) < 8
                        and not (qc & {'wifi5', 'wifi6'}) - p[1]['_c']):
                    cerca.append(p)
                    vistas.add(p[1].get('_marca'))
        # un solo producto con distinto largo/variante no es ambigüedad si el pedido nombró el modelo exacto
        if len(cerca) == 1 or (qm and top >= 80 and (len(cerca) == 1 or cerca[1][0][0] < top - 1)):
            res.update(estado='CUMPLE', item=cerca[0][1])
            res['notas'] += cerca[0][0][1]
        else:
            res.update(estado='OPCIONES', opciones=[(p[1], p[0][1]) for p in cerca])
            marcas = {p[1].get('_marca') or '?' for p in cerca}
            if len(marcas) > 1 and not re.search(MARCA_PED, t) and qc & {'ont', 'placa', 'olt', 'sfp'}:
                res['notas'].append('hay opciones de más de una marca: preguntar la OLT del cliente antes de elegir (D05)')
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


def aplicar_hive(cat, hive, hoy=None):
    """1.2.0: reemplaza el stock R8 por el de Hive en los códigos consultados y marca diferencias de precio y ETA vencidas.
    hive = {"consultado": F, "productos": {cod: {"stock": datos de consultar_stock, "precio": datos de precio_producto}}}."""
    prods = (hive or {}).get('productos') or {}
    hoy = hoy or (hive or {}).get('consultado') or ''
    snaps = set()
    for s in cat['stock']:
        h = prods.get(s['cod'])
        if not h or not isinstance(h.get('stock'), dict):
            continue
        st = h['stock']
        tot = ((st.get('stock') or {}).get('total'))
        if tot is None:
            continue
        tr = st.get('transito') or {}
        pr = st.get('produccion') or {}
        etas = sorted(l.get('eta') for l in (tr.get('lotes') or []) if l.get('eta'))
        disp = st.get('disponibilidad')
        s['hive'] = {'snapshot': st.get('snapshot_fecha'), 'stock': float(tot), 'transito': float(tr.get('total') or 0),
                     'eta': etas[0] if etas else None, 'produccion': float(pr.get('total') or 0),
                     'disponible': (disp or {}).get('disponible') if isinstance(disp, dict) else disp}
        if st.get('snapshot_fecha'):
            snaps.add(st['snapshot_fecha'])
    for it in cat['items']:
        for s in it['stock']:
            h = prods.get(s['cod'])
            pr = (h or {}).get('precio')
            if not isinstance(pr, dict):
                continue
            isp = next((n.get('precio') for n in pr.get('niveles') or [] if norm(n.get('nivel')) == 'isp'), None)
            if isp is not None:
                it['_hive_isp'] = isp
                if it.get('precio') is not None and abs(float(isp) - float(it['precio'])) > 0.005:
                    it['_hive_dif'] = f"precio ISP en Hive USD {isp:g} ≠ lista CRM USD {it['precio']:g}: confirmar cuál vale"
    cat['_hive'] = {'consultado': hoy, 'snapshot': max(snaps) if snaps else None}
    return cat


def stock_txt(it_o_s):
    ss = it_o_s.get('stock') if 'precio' in it_o_s else [it_o_s]
    if not ss:
        return 'stock: sin código en R8'
    if any(s.get('hive') for s in ss):
        h = [s['hive'] for s in ss if s.get('hive')]
        resto = [s for s in ss if not s.get('hive')]
        cod = '/'.join(sorted({s['cod'] for s in ss if s.get('hive')}))
        t = f"cód. {cod} · stock Hive {sum(x['stock'] for x in h):,.0f}".replace(',', '.')
        if resto:   # códigos que Hive no tiene: siguen con R8 y se dicen aparte
            t += ' · ' + '; '.join(f"cód. {s['cod']} sin dato en Hive (R8: {s['stock']:,.0f})".replace(',', '.') for s in resto)
        disp = [x['disponible'] for x in h if x.get('disponible') is not None]
        if disp:
            t += f' (disponible {sum(disp):,.0f})'.replace(',', '.')
        else:   # Hive no informa reservas: se muestra lo comprometido del R8 con su fuente
            ped = sum(s['pedidos'] for s in ss)
            if ped:
                t += f' (comprometido R8 {ped:,.0f})'.replace(',', '.')
        trn = sum(x['transito'] for x in h)
        if trn:
            eta = min((x['eta'] for x in h if x.get('eta')), default=None)
            t += f' · tránsito {trn:,.0f}'.replace(',', '.') + (f' (ETA {eta})' if eta else '')
        prd = sum(x['produccion'] for x in h)
        if prd:
            t += f' · producción {prd:,.0f}'.replace(',', '.')
        return t
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
            out.append(f"   {stock_txt(it)} · precio: {it['fuente']}" + (f" · ficha: {it['_ficha']}" if it.get('_ficha') else ' · sin ficha técnica'))
            for n in _hive_avisos(cat, it):
                out.append(f'   ojo: {n}')
                revisar.append(f'{i}: {n}')
            if r['cant'] is None:
                revisar.append(f'{i}: falta la cantidad')
        for it, notas in r['opciones']:
            pt, _ = renglon_precio(it, r['cant'])
            out.append(f"   ? {it['nombre']} · {pt} · {stock_txt(it)}" + (f" · ficha: {it['_ficha']}" if it.get('_ficha') else '')
                       + (f" · {'; '.join(notas)}" if notas else ''))
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
    hv = cat.get('_hive')
    stk = (f"stock Hive/Comb foto {hv['snapshot'] or '?'} (consultado {hv['consultado']}; lo no consultado sigue con R8 {corte.get('R8', '?')})"
           if hv else f"stock R8 {corte.get('R8', '?')}")
    out.append(f"Fuentes: lista CRM {corte.get('crm:lista', '?')} · {stk} (sujeto a confirmación con JP) · "
               f'precios especiales del cliente: no están en la base · motor.py {VERSION}')
    return '\n'.join(out)


def _hive_avisos(cat, it):
    """1.2.0: avisos de Hive para un producto elegido: precio distinto de la lista y ETA de tránsito vencida."""
    hv = cat.get('_hive')
    if not hv:
        return []
    av = [it['_hive_dif']] if it.get('_hive_dif') else []
    hoy = hv.get('consultado') or ''
    for s in it['stock']:
        e = (s.get('hive') or {}).get('eta')
        if e and hoy and e < hoy and (s['hive'].get('transito') or 0) > 0:
            av.append(f"ETA del tránsito ({e}) ya venció: confirmar con JP si llegó")
            break
    return av


def codigos(cat, texto):
    """1.2.0: códigos de Finnegans de lo que el motor elegiría (CUMPLE, OPCIONES o SIN PRECIO), para consultarlos en Hive."""
    cs = []
    for l in partir_pedido(texto):
        r = cruzar(cat, l)
        its = ([r['item']] if r['item'] else []) + [o[0] for o in r['opciones']]
        for it in its:
            cs += [s['cod'] for s in it['stock']]
        cs += [s['cod'] for s in r['sinprecio']]
    vistos = []
    for c in cs:
        if c not in vistos:
            vistos.append(c)
    return vistos


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
        {'id': 'an60002', 'nombre': 'OLT AN6000-2', 'cat': 'OLT y placas', 'precio': 2020, 'iva': '10.5%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'an60007', 'nombre': 'OLT AN6000-7', 'cat': 'OLT y placas', 'precio': 3950, 'iva': '10.5%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'gpoa', 'nombre': 'Placa GPOA C++', 'cat': 'OLT y placas', 'precio': 2190, 'iva': '10.5%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'esr', 'nombre': 'Placa ESR-PRE2 10000', 'cat': 'OLT y placas', 'precio': 1150, 'iva': '21%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'sr1041f', 'nombre': 'Router wireless SR1041F', 'cat': 'ONT / ONU', 'precio': 37, 'iva': '10.5%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'precon8', 'nombre': 'Caja NAP FH Preconectorizada 1x8', 'cat': 'Cajas, NAP y distribución', 'precio': 38.3, 'iva': '21%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
        {'id': 'sp18', 'nombre': 'Splitter optico FH 1x4 NC - SC/APC', 'cat': 'Cajas, NAP y distribución', 'precio': 4.94, 'iva': '21%', 'unidad': 'unidad', 'fuente': 'L', 'stock': [], 'sub': ''},
    ]
    stock = [it['stock'][0] for it in items if it['stock']] + [{'cod': '1070', 'nombre': 'Caja de empalme optico CEO II FM DPR', 'sub': '', 'stock': 0, 'pedidos': 0, 'total': 0}]
    fichas = [{'modelo': 'HG6145F3', 'buscar': '%HG6145F3%', 'specs': [['WiFi', 'AX3000 · 802.11ax 2,4 + 5 GHz']]},
              {'modelo': 'FitDP-420A', 'buscar': '%420A%', 'specs': [['Splitter', 'A1 y A3: 2 de 1x8 · A2: 1 de 1x16']]},
              {'modelo': 'SR1041F', 'buscar': '%SR1041F%', 'specs': [['WiFi', 'AX3000 · OFDMA']]}]
    cat = preparar(items, stock, [{'alias': 'king box', 'producto': '420a'}], fichas)
    casos = [
        ('20 onus wifi 5', 'CUMPLE', 'hg6543d'), ('HG6543D', 'CUMPLE', 'hg6543d'), ('1114', 'CUMPLE', 'hg6543d'),
        ('10 botellas de 48', 'CUMPLE', 'ce48'), ('5 domos 144 fibras', 'CUMPLE', 'ce144'), ('4 km de drop', 'CUMPLE', 'drop'),
        ('8000 m adss 48f', 'CUMPLE', 'as80-48'), ('2 placas GPUF 16 port C+', 'CUMPLE', 'gpuf'), ('50 king box', 'CUMPLE', '420a'),
        ('100 onu wifi 6', 'OPCIONES', None), ('100 onu wifi 6 fiberhome', 'CUMPLE', 'hg6145f3'),
        ('100 onu wifi 6 huawei', 'CUMPLE', 'eg8145'), ('1 olt chica', 'CUMPLE', 'an60002'), ('10 nap de 16', 'CUMPLE', '420a'),
        ('5 nap 1x16', 'CUMPLE', '420a'), ('una caja de 1x8', 'OPCIONES', None), ('10 routers wifi 6', 'CUMPLE', 'sr1041f'),
        ('ESR-PRE2', 'CUMPLE', 'esr'), ('30 onu solo datos', 'CUMPLE', 'an5506'), ('1070', 'SIN PRECIO', None),
        ('3 licuadoras', 'NO TENEMOS', None), ('25 onus', 'OPCIONES', None), ('20 cajas nap', 'OPCIONES', None),
    ]
    ok = 0
    for txt, est, iid in casos:
        r = cruzar(cat, txt)
        bien = r['estado'] == est and (iid is None or (r['item'] or {}).get('id') == iid)
        ok += bien
        print(('PASA ' if bien else 'FALLA'), txt, '→', r['estado'], (r['item'] or {}).get('id'))
    r = cruzar(cat, '2 placas gpon')
    ok += all(o[0]['id'] != 'esr' for o in r['opciones']) and (r['item'] or {}).get('id') != 'esr'
    print(('PASA ' if all(o[0]['id'] != 'esr' for o in r['opciones']) else 'FALLA'), 'discontinuado fuera de «2 placas gpon» (D06)')
    q_, u, _ = cantidad('4 km de drop')
    ok2 = q_ == 4000 and u == 'm'
    print(('PASA ' if ok2 else 'FALLA'), 'cantidad 4 km = 4000 m')
    q_, u, _ = cantidad('4.000 m de adss')
    ok3 = q_ == 4000
    print(('PASA ' if ok3 else 'FALLA'), 'cantidad 4.000 m')
    # 1.2.0: Hive reemplaza el stock R8 del código consultado, avisa precio distinto y ETA vencida, y no toca lo no consultado
    hv = {'consultado': '2026-11-20', 'productos': {'1114': {
        'stock': {'snapshot_fecha': '2026-11-17', 'stock': {'total': 950}, 'transito': {'total': 400, 'lotes': [{'cantidad': 400, 'eta': '2026-10-29'}]},
                  'produccion': {'total': 100}, 'disponibilidad': None},
        'precio': {'niveles': [{'nivel': 'Precio de Lista', 'precio': 27}, {'nivel': 'ISP', 'precio': 26}]}}}}
    aplicar_hive(cat, hv)
    it = next(i for i in cat['items'] if i['id'] == 'hg6543d')
    txt, av = stock_txt(it), _hive_avisos(cat, it)
    ok4 = ('stock Hive 950' in txt and 'tránsito 400 (ETA 2026-10-29)' in txt and 'producción 100' in txt
           and any('26' in a and '25.5' in a for a in av) and any('venció' in a for a in av) and it['precio'] == 25.5)
    print(('PASA ' if ok4 else 'FALLA'), 'Hive: stock, tránsito, producción, precio distinto (sin pisar la lista) y ETA vencida ·', txt, av)
    ok5 = codigos(cat, '20 onus wifi 5') == ['1114'] and 'Hive' in responder(cat, {'crm:lista': 'x', 'R8': 'y'}, '20 onus wifi 5')
    print(('PASA ' if ok5 else 'FALLA'), 'codigos() y fuentes con Hive')
    n = len(casos) + 5
    tot = ok + ok2 + ok3 + ok4 + ok5
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
        hv = None
        if '--hive' in a:
            k = a.index('--hive')
            hv = json.load(open(a[k + 1], encoding='utf-8'))
            a = a[:k] + a[k + 2:]
            aplicar_hive(cat, hv)
        if a[0] == 'responder':
            texto = open(a[2], encoding='utf-8').read() if len(a) > 2 and a[1] == '-f' else ' '.join(a[1:])
            print(responder(cat, corte, texto))
        elif a[0] == 'codigos':
            texto = open(a[2], encoding='utf-8').read() if len(a) > 2 and a[1] == '-f' else ' '.join(a[1:])
            print(' '.join(codigos(cat, texto)) or 'sin códigos')
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
