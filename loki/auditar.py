#!/usr/bin/env python3
"""Auditor de archivos que entran al Data Center de Horizon (reportes de Finnegans y respaldo del CRM).

Uso (siempre con python3 -I, desde otra carpeta que los datos):
  auditar.py archivo RUTA BASE [AAAA-MM-DD]   audita un archivo contra la version cargada
  auditar.py todo BASE [AAAA-MM-DD]           audita todo lo cargado y cruza reportes entre si

BASE tiene la version vigente: R10.csv + R10.json (el documento de reportes/R10) y, para el
respaldo, respaldo_meta.json. Sale un JSON con veredicto:
  OK        se puede subir
  AVISOS    se puede subir, pero hay que mirar lo marcado
  NO_SUBIR  hay un problema grave

No escribe en ningun lado: solo lee y calcula.
"""
import difflib
import unicodedata
import csv, datetime as D, glob, hashlib, io, json, os, re, sys
from collections import Counter

# 1.1 (17/11): R24 pedidos por renglón ampliado, R25 maestro de productos (PRIVADO: costo), R26 remitos de venta por renglón.
ACUMULATIVOS = {'R4', 'R6', 'R7', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15', 'R20', 'R21', 'R23', 'R24', 'R26'}
FOTOS = {'R5', 'R8', 'R22', 'R25'}
CLAVE = {'R4': ['Documento', 'Nro comp'], 'R15': ['Documento', 'Nro comp'], 'R5': ['Doc.-nro. interno'],
         'R6': ['Doc.-nro. interno'], 'R7': ['Doc.-nro. interno'], 'R10': ['Doc.-nro. interno'],
         'R11': ['Doc.-nro. interno'], 'R12': ['Doc.-nro. interno'], 'R13': ['Doc.-nro. interno'],
         'R14': ['Doc.-nro. interno'], 'R8': ['Productoid'], 'R24': ['Doc.-nro. interno'],
         'R26': ['Comprobante'], 'R25': ['ProductoID']}
NUMERICAS = ['Cantidad', 'Importe', 'Precio', 'Total', 'Stock', 'Pte Dest.']
COMPARAR = ['Cantidad', 'Importe']
MAX_EJ = 5
MOJIBAKE = re.compile('Ã[\u0080-¿¡-¿]|�')
NUM_PUNTO = re.compile(r'^-?\d+(\.\d+)?$')
NUM_COMA = re.compile(r'^-?\d{1,3}(\.\d{3})*,\d+$|^-?\d+,\d+$')
ISO = re.compile(r'^\d{4}-\d{2}-\d{2}')
DMY = re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{4})')


def low(s):
    return (s or '').strip().lower()


def col(h, nombre):
    n = low(nombre)
    for c in h:
        if low(c) == n:
            return c
    return None


def leer_num(s):
    """Devuelve (valor, formato) con formato 'punto', 'coma', 'vacio' o 'malo'."""
    s = (s or '').strip()
    if not s:
        return None, 'vacio'
    if NUM_PUNTO.match(s):
        return float(s), 'punto'
    if NUM_COMA.match(s):
        return float(s.replace('.', '').replace(',', '.')), 'coma'
    try:
        return float(s), 'punto'
    except ValueError:
        return None, 'malo'


def leer_fecha(s):
    """Devuelve (fecha, formato) con formato 'iso', 'dmy', 'vacio' o 'malo'."""
    s = (s or '').strip()
    if not s:
        return None, 'vacio'
    try:
        if ISO.match(s):
            return D.date.fromisoformat(s[:10]), 'iso'
        m = DMY.match(s)
        if m:
            return D.date(int(m[3]), int(m[2]), int(m[1])), 'dmy'
    except ValueError:
        pass
    return None, 'malo'


def leer_tabla(ruta):
    """Devuelve dict con encabezado, filas (listas), desparejas, texto_lineas, formato, encoding."""
    raw = open(ruta, 'rb').read()
    if raw[:2] == b'PK' or ruta.lower().endswith('.xlsx'):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        todas = []
        for f in wb[wb.sheetnames[0]].iter_rows(values_only=True):
            todas.append(['' if v is None else (v.date().isoformat() if isinstance(v, D.datetime)
                          else v.isoformat() if isinstance(v, D.date) else str(v)) for v in f])
        ini = max(range(min(15, len(todas))), key=lambda i: sum(1 for v in todas[i] if v), default=0) if todas else 0
        h = [v for v in todas[ini]] if todas else []
        while h and not h[-1]:
            h.pop()
        filas = [f[:len(h)] for f in todas[ini + 1:] if any(f)]
        return dict(h=h, filas=filas, desparejas=0, formato='xlsx', encoding='xlsx', sha=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    enc = 'utf-8-sig'
    try:
        txt = raw.decode(enc)
    except UnicodeDecodeError:
        enc = 'cp1252'
        txt = raw.decode(enc, 'replace')
    prim = txt.split('\n', 1)[0]
    sep = max(';,\t', key=prim.count)
    r = list(csv.reader(io.StringIO(txt), delimiter=sep))
    r = [f for f in r if any(c.strip() for c in f)]
    if not r:
        return dict(h=[], filas=[], desparejas=0, formato='csv', encoding=enc, sep=sep, sha=hashlib.sha256(raw).hexdigest(), bytes=len(raw), txt=txt)
    h, cuerpo = r[0], r[1:]
    desp = sum(1 for f in cuerpo if len(f) != len(h))
    return dict(h=h, filas=cuerpo, desparejas=desp, formato='csv', encoding=enc, sep=sep, sha=hashlib.sha256(raw).hexdigest(), bytes=len(raw), txt=txt)


def como_dict(t):
    """Cada fila como dict; si una columna se repite vale la primera aparicion."""
    idx = {}
    for i, c in enumerate(t['h']):
        idx.setdefault(c, i)
    return [{c: (f[i] if i < len(f) else '') for c, i in idx.items()} for f in t['filas']]


def metas(base):
    m = {}
    for f in glob.glob(os.path.join(base, 'R*.json')):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if d.get('codigo') and d.get('columnas'):
            m[d['codigo']] = d
    return m


def orden(c):
    return int(c[1:])


def identificar(h, nombre, ms):
    """Devuelve (codigo, parecido). Columnas iguales ganan; R4 va antes que su duplicado R15."""
    s = {low(c) for c in h}
    pista = re.search(r'reporte[_ ]?(\d+)', nombre, re.I)
    pista = 'R' + pista[1] if pista else None
    mejor, val = None, -1.0
    for c in sorted(ms, key=orden):
        o = {low(x) for x in ms[c]['columnas']}
        j = len(s & o) / max(len(s | o), 1)
        if j > val or (j == val and c == pista):
            mejor, val = c, j
    return mejor, val


def resumen(filas, h, cod):
    """Calcula lo que hace falta de una tabla: fechas, claves, sumas, formatos."""
    r = dict(n=len(filas), fechas_malas=0, formatos_fecha=Counter(), formatos_num=Counter(), num_malos=[],
             desde=None, hasta=None, sin_cliente=0, empresas=Counter(), nc_pos=set(), neg_stock=0,
             claves={}, primer_fecha={})
    cf = col(h, 'Fecha')
    cc = col(h, 'Cliente')
    ce = col(h, 'Empresa')
    cd = col(h, 'Documento')
    ci = col(h, 'Doc.-nro. interno')
    ck = [col(h, x) for x in CLAVE.get(cod, [])]
    ck = ck if ck and all(ck) else []
    nums = [c for c in (col(h, x) for x in NUMERICAS) if c]
    comp = [c for c in (col(h, x) for x in (COMPARAR + ['Total'] if cod in ('R4', 'R15') else COMPARAR)) if c]
    ccant = col(h, 'Cantidad')
    cstock = col(h, 'Stock') if cod == 'R8' else None
    for i, f in enumerate(filas):
        fe = None
        if cf:
            fe, fmt = leer_fecha(f.get(cf))
            r['formatos_fecha'][fmt] += 1
            if fmt == 'malo' or (fmt == 'vacio' and cod not in FOTOS):
                r['fechas_malas'] += 1
            if fe:
                r['desde'] = min(r['desde'] or fe, fe)
                r['hasta'] = max(r['hasta'] or fe, fe)
        if cc and not (f.get(cc) or '').strip():
            r['sin_cliente'] += 1
        if ce:
            r['empresas'][(f.get(ce) or '').strip()] += 1
        vals = {}
        for c in nums:
            v, fmt = leer_num(f.get(c))
            r['formatos_num'][fmt] += 1
            if fmt == 'malo' and len(r['num_malos']) < MAX_EJ:
                r['num_malos'].append(f'{c}={f.get(c)!r} fila {i + 2}')
            if fmt == 'malo':
                r['formatos_num']['malos_total'] += 1
            vals[c] = v or 0.0
        if cstock and vals.get(cstock, 0) < 0:
            r['neg_stock'] += 1
        tipo = ((f.get(cd) if cd else '') or '') + ' ' + ((f.get(ci) if ci else '') or '')
        if ccant and re.search(r'nota de cr[eé]dito|\bNCV', tipo, re.I) and vals.get(ccant, 0) > 0 and not re.search('descuento', str(f.get(col(h, 'Producto') or '', '')), re.I):
            r['nc_pos'].add('|'.join(str(f.get(c, '')) for c in (ck or [ccant])) + '|' + str(f.get(col(h, 'Producto') or '', '')))
        if ck:
            k = ' | '.join((f.get(c) or '').strip() for c in ck)
            ac = r['claves'].setdefault(k, {c: 0.0 for c in comp})
            for c in comp:
                ac[c] += vals.get(c, 0)
            if fe:
                r['primer_fecha'][k] = fe
    return r


def duplicadas(t):
    return t['n_lineas'] - t['n_unicas']


def preparar(t):
    lineas = ['\x1f'.join(f) for f in t['filas']]
    t['n_lineas'], t['n_unicas'] = len(lineas), len(set(lineas))
    return t


def fmt(d):
    return d.isoformat() if d else None


def ej(lista):
    lista = sorted(lista)
    return ', '.join(lista[:MAX_EJ]) + (f' y {len(lista) - MAX_EJ} más' if len(lista) > MAX_EJ else '')


def auditar_reporte(ruta, base, hoy, nombre=None, contra_base=True):
    nombre = nombre or os.path.basename(ruta)
    salida = dict(archivo=nombre, tipo=None, graves=[], avisos=[], info=[])
    g, a, inf = salida['graves'], salida['avisos'], salida['info']
    try:
        t = leer_tabla(ruta)
    except Exception as e:
        g.append(f'No se pudo leer el archivo ({type(e).__name__})')
        return cerrar(salida)
    if not t['h']:
        g.append('El archivo está vacío')
        return cerrar(salida)
    ms = metas(base)
    cod, parecido = identificar(t['h'], nombre, ms)
    if not cod or parecido < 0.6:
        g.append(f'No coincide con ningún reporte conocido (parecido {parecido:.0%})')
        return cerrar(salida)
    salida['tipo'] = cod
    if parecido < 1:
        inf.append(f'Identificado por parecido: {parecido:.0%} con {cod}')
    pista = re.search(r'reporte[_ ]?(\d+)', nombre, re.I)
    if pista and 'R' + pista[1] != cod and {cod, 'R' + pista[1]} != {'R4', 'R15'}:
        a.append(f'El nombre dice R{pista[1]} y el contenido es {cod}')
    if t['formato'] == 'xlsx':
        a.append('Vino en Excel: los motores leen CSV, hay que convertirlo o exportarlo en CSV antes de usarlo')
    meta = ms[cod]
    esperadas = {low(c): c for c in meta['columnas']}
    actuales = {low(c) for c in t['h']}
    faltan = [v for k, v in esperadas.items() if k not in actuales]
    sobran = [c for c in t['h'] if low(c) not in esperadas]
    if faltan:
        g.append(f'Faltan {len(faltan)} columnas: ' + ej(faltan))
    if sobran:
        a.append(f'Columnas nuevas ({len(sobran)}): ' + ej(sobran))
    if t['desparejas']:
        g.append(f"{t['desparejas']} filas con distinta cantidad de campos: archivo cortado o separador mal")
    if not t['filas']:
        (a if cod in FOTOS else g).append('No trae filas')
        return cerrar(salida)
    preparar(t)
    filas = como_dict(t)
    r = resumen(filas, t['h'], cod)
    if t.get('txt') and MOJIBAKE.search(t['txt']):
        g.append('Acentos rotos: el archivo se exportó con otra codificación')
    if t['encoding'] == 'cp1252':
        inf.append('Codificación Windows-1252, se pasa a UTF-8 al subir')
    if r['formatos_fecha'].get('dmy'):
        g.append(f"{r['formatos_fecha']['dmy']} fechas en formato dd/mm/aaaa: los motores esperan aaaa-mm-dd")
    if r['fechas_malas']:
        g.append(f"{r['fechas_malas']} filas con fecha vacía o ilegible")
    if r['formatos_num'].get('coma'):
        g.append(f"{r['formatos_num']['coma']} números con coma decimal: los motores esperan punto")
    if r['formatos_num'].get('malos_total'):
        g.append(f"{r['formatos_num']['malos_total']} números ilegibles: " + ej(r['num_malos']))
    if r['hasta'] and r['hasta'] > hoy:
        g.append(f"Fecha futura: {fmt(r['hasta'])}")
    if cod in ACUMULATIVOS and r['hasta'] and (hoy - r['hasta']).days > 7:
        a.append(f"Corte viejo: el último dato es del {fmt(r['hasta'])}")
    if r['neg_stock']:
        a.append(f"{r['neg_stock']} productos con stock negativo")
    salida['meta'] = dict(filas=r['n'], desde=fmt(r['desde']), hasta=fmt(r['hasta']), columnas=len(t['h']), bytes=t['bytes'], sha256=t['sha'], duplicadas=duplicadas(t), nc_cantidad_positiva=len(r['nc_pos']))

    previo = os.path.join(base, cod + '.csv')
    if not contra_base:
        return cerrar(salida)
    if not os.path.exists(previo):
        a.append('No hay versión anterior para comparar')
        return cerrar(salida)
    tp = preparar(leer_tabla(previo))
    if tp['sha'] == t['sha'] or (t['formato'] == 'csv' and tp['h'] == t['h'] and tp['filas'] == t['filas']):
        inf.append('Es idéntico al que ya está cargado: no hace falta subirlo')
        return cerrar(salida)
    p = resumen(como_dict(tp), tp['h'], cod)
    delta = r['n'] - p['n']
    salida['meta']['filas_antes'] = p['n']
    if cod in ACUMULATIVOS:
        if delta < 0:
            g.append(f"Trae {-delta} filas menos que la versión cargada ({r['n']} contra {p['n']})")
        if r['hasta'] and p['hasta'] and r['hasta'] < p['hasta']:
            g.append(f"Es más viejo que el cargado: llega al {fmt(r['hasta'])} y el cargado al {fmt(p['hasta'])}")
        if r['desde'] and p['desde'] and r['desde'] > p['desde']:
            g.append(f"Empieza más tarde que el cargado: {fmt(r['desde'])} contra {fmt(p['desde'])}")
    elif p['n'] and r['n'] < p['n'] * 0.7 and cod == 'R8':
        a.append(f"Stock con muchas menos filas: {r['n']} contra {p['n']}")
    dup_nuevas = duplicadas(t) - duplicadas(tp)
    if dup_nuevas > max(5, r['n'] * 0.01):
        g.append(f'{dup_nuevas} filas repetidas más que antes: posible archivo duplicado')
    elif dup_nuevas > 0:
        a.append(f'{dup_nuevas} filas repetidas nuevas')
    psc, rsc = p['sin_cliente'], r['sin_cliente']
    if rsc > psc:
        (g if rsc > r['n'] * 0.05 else a).append(f'{rsc} filas sin cliente (antes {psc})')
    nuevas_emp = [e for e in r['empresas'] if e not in p['empresas']]
    if nuevas_emp:
        g.append('Empresa que antes no venía: ' + ej(nuevas_emp))
    nc_nuevas = r['nc_pos'] - p['nc_pos']
    if nc_nuevas:
        a.append(f'{len(nc_nuevas)} renglones nuevos de nota de crédito con cantidad positiva: revisar el signo. ' + ej(nc_nuevas))
    if cod in ACUMULATIVOS and p['claves'] and r['claves']:
        corte_ini = r['desde'] or p['desde']
        ausentes = [k for k in p['claves'] if k not in r['claves'] and (not corte_ini or not p['primer_fecha'].get(k) or p['primer_fecha'][k] >= corte_ini)]
        if ausentes:
            lim = max(3, len(p['claves']) * 0.01)
            (g if len(ausentes) > lim else a).append(f'Desaparecieron {len(ausentes)} comprobantes: ' + ej(ausentes))
        cambiados = [k for k in p['claves'] if k in r['claves'] and any(abs(p['claves'][k][c] - r['claves'][k].get(c, 0)) > 0.01 for c in p['claves'][k])]
        if cambiados:
            a.append(f'Cambiaron cantidad o importe en {len(cambiados)} comprobantes ya cargados: ' + ej(cambiados))
        nuevos = [k for k in r['claves'] if k not in p['claves']]
        inf.append(f'{len(nuevos)} comprobantes nuevos')
        if p['hasta']:
            atras = [k for k in nuevos if r['primer_fecha'].get(k) and r['primer_fecha'][k] < p['hasta']]
            if atras:
                a.append(f"{len(atras)} comprobantes nuevos con fecha anterior al corte cargado: " + ej(atras))
    return cerrar(salida)


def cerrar(s):
    s['veredicto'] = 'NO_SUBIR' if s['graves'] else 'AVISOS' if s['avisos'] else 'OK'
    return s


def auditar_respaldo(ruta, base, hoy, d):
    s = dict(archivo=os.path.basename(ruta), tipo='respaldo CRM', graves=[], avisos=[], info=[])
    g, a, inf = s['graves'], s['avisos'], s['info']
    col_ = d.get('collections') or {}
    cuenta = {k: len(v or []) for k, v in col_.items()}
    for k in ('oportunidades', 'cotizaciones'):
        if not cuenta.get(k):
            g.append(f'El respaldo no trae {k}')
    exp = leer_fecha((d.get('exportedAt') or d.get('exportadoEn')) or '')[0]
    meta_p = os.path.join(base, 'respaldo_meta.json')
    pm = json.load(open(meta_p, encoding='utf-8')) if os.path.exists(meta_p) else {}
    if exp and (hoy - exp).days > 3:
        a.append(f'Respaldo viejo: {fmt(exp)}')
    if not exp:
        a.append('El respaldo no dice cuándo se exportó')
    pe = leer_fecha(pm.get('exportadoEn') or '')[0]
    pe_txt, nu_txt = pm.get('exportadoEn') or '', (d.get('exportedAt') or d.get('exportadoEn')) or ''
    if exp and pe and nu_txt < pe_txt:
        g.append(f'Es más viejo que el cargado: {fmt(exp)} contra {fmt(pe)}')
    elif pe_txt and nu_txt == pe_txt:
        inf.append('Tiene la misma fecha de exportación que el cargado')
    for k, n in (pm.get('colecciones') or {}).items():
        act = cuenta.get(k, 0)
        if act < n:
            grave = k in ('oportunidades', 'cotizaciones', 'lista') and (n - act) > max(1, n * 0.02)
            (g if grave or act == 0 else a).append(f'{k}: {act} contra {n} del cargado')
    raw = open(ruta, 'rb').read()
    s['meta'] = dict(colecciones=cuenta, exportadoEn=(d.get('exportedAt') or d.get('exportadoEn')), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return cerrar(s)


def auditar(ruta, base, hoy):
    if ruta.lower().endswith('.json'):
        try:
            d = json.load(open(ruta, encoding='utf-8-sig'))
        except Exception as e:
            return cerrar(dict(archivo=os.path.basename(ruta), tipo=None, graves=[f'JSON ilegible ({type(e).__name__}): archivo cortado o dañado'], avisos=[], info=[]))
        if isinstance(d, dict) and 'collections' in d:
            return auditar_respaldo(ruta, base, hoy, d)
        return cerrar(dict(archivo=os.path.basename(ruta), tipo=None, graves=['El JSON no es un respaldo del CRM'], avisos=[], info=[]))
    return auditar_reporte(ruta, base, hoy)


# ===== MEDICION DE CRUCES (solo mide: no cambia el veredicto) =====
NO_MERCA = re.compile(r'diferencia de cambio|anticipo|descuento|honorario|flete|servicio|intereses?|ajuste', re.I)
SOC = {'sa', 'srl', 'sas', 'sapem', 'ltda', 'limitada', 'sau', 'sociedad', 'anonima', 'responsabilidad', 'cv', 'y', 'de', 'la', 'el'}


def sin_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def norm_cli(s):
    t = re.sub(r'\b([a-z])\.\s*(?=[a-z]\.)', r'\1', sin_acento(low(s)))
    t = re.sub(r'[^a-z0-9 ]', '', t.replace('.', ''))
    return ' '.join(x for x in t.split() if x not in SOC)


def norm_prod(s):
    return ' '.join(sin_acento(low(s)).split())


def num(s):
    return leer_num(s)[0] or 0.0


def fecha(s):
    return leer_fecha(s)[0]


def tabla(base, c):
    ruta = os.path.join(base, c + '.csv')
    return como_dict(leer_tabla(ruta)) if os.path.exists(ruta) else None


def top(lista, k, n=MAX_EJ):
    return sorted(lista, key=lambda x: -abs(x[k]))[:n]


def es_nc(doc):
    return 'crédito' in low(doc) or 'credito' in low(doc)


def es_cambio(doc):
    return 'dif. cambio' in low(doc)


def cruce_r10_r4(r10, r4):
    desde = min(d for d in (fecha(x.get('Fecha')) for x in r10) if d)
    a, cab = {}, {}
    for x in r10:
        k = (x['Documento'].strip(), x['Comprobante'].strip())
        v = a.setdefault(k, dict(imp=0.0, bruto=num(x.get('Bruto')), cli=x['Cliente'].strip(), fecha=x['Fecha'][:10], mon=x.get('Moneda', '')))
        v['imp'] += num(x.get('Importe'))
    for x in r4:
        if (fecha(x.get('Fecha')) or D.date.min) >= desde:
            cab[(x['Documento'].strip(), x['Nro comp'].strip())] = x
    solo10 = [dict(comp=k[1], cliente=v['cli'], fecha=v['fecha'], importe=round(v['imp'], 2)) for k, v in a.items() if k not in cab]
    solo4 = [dict(comp=k[1], cliente=x['Cliente'].strip(), fecha=x['Fecha'][:10], bruto=round(num(x.get('Bruto')), 2), doc=k[0]) for k, x in cab.items() if k not in a]
    dif = []
    for k, v in a.items():
        if k in cab:
            b = num(cab[k].get('Bruto'))
            if abs(abs(v['bruto']) - abs(b)) > 0.05:
                dif.append(dict(comp=k[1], cliente=v['cli'], r10=round(v['bruto'], 2), r4=round(b, 2), dif=round(abs(v['bruto']) - abs(b), 2)))
    return dict(comprobantes_r10=len(a), comprobantes_r4=len(cab), coinciden=len(set(a) & set(cab)), solo_r10=len(solo10), solo_r4=len(solo4), bruto_distinto=len(dif),
                ej_solo_r10=top(solo10, 'importe'), ej_solo_r4=top(solo4, 'bruto'), ej_bruto_distinto=top(dif, 'dif'))


def cruce_pte_r13(r10, r13, r8):
    """Pte Dest. ya viene neto de remitos: se compara facturado - remitido contra Pte Dest."""
    pte, rem = {}, {}
    for x in r10:
        p = num(x.get('Pte Dest.'))
        if p > 0 and not es_cambio(x['Documento']) and not es_nc(x['Documento']):
            k = (norm_cli(x['Cliente']), norm_prod(x['Producto']))
            v = pte.setdefault(k, dict(cliente=x['Cliente'].strip(), producto=x['Producto'].strip(), pendiente=0.0, facturado=0.0, desde=fecha(x['Fecha'])))
            v['pendiente'] += p
            v['facturado'] += num(x.get('Cantidad'))
            v['desde'] = min(v['desde'], fecha(x['Fecha']))
    for x in r13:
        k = (norm_cli(x['Cliente']), norm_prod(x['Producto']))
        if k in pte and (fecha(x.get('Fecha')) or D.date.min) >= pte[k]['desde']:
            sg = -1 if 'devoluci' in low(x.get('Transacconsubtiponombre')) else 1
            rem[k] = rem.get(k, 0.0) + sg * abs(num(x.get('Cantidad')))
    cuadra, no = [], []
    for k, v in pte.items():
        r = rem.get(k, 0.0)
        esperado = max(v['facturado'] - r, 0.0)
        f = dict(cliente=v['cliente'], producto=v['producto'], facturado=round(v['facturado'], 2), remitido=round(r, 2), pte_r10=round(v['pendiente'], 2), esperado=round(esperado, 2), dif=round(v['pendiente'] - esperado, 2), desde=v['desde'].isoformat())
        (cuadra if abs(f['dif']) <= 0.5 else no).append(f)
    con_dato = sum(1 for x in r8 or [] if num(x.get('Facturas de venta s/r')) > 0.5)
    return dict(pares=len(pte), cuadran=len(cuadra), no_cuadran=len(no), unidades_pendientes=round(sum(v['pendiente'] for v in pte.values()), 2), ej_no_cuadran=top(no, 'dif', 10), r8_columna_facturas_sr='vacia' if not con_dato else con_dato)


def cruce_r12_r10(r12, r10, r5):
    ped, fac, usd = {}, {}, {}
    nombre = {}
    for x in r12:
        if NO_MERCA.search(x['Producto']):
            continue
        k = (norm_cli(x['Cliente']), norm_prod(x['Producto']))
        ped[k] = ped.get(k, 0.0) + num(x.get('Cantidad'))
        nombre.setdefault(k, (x['Cliente'].strip(), x['Producto'].strip()))
        if low(x.get('Moneda')).startswith('d') and num(x.get('Cantidad')):
            usd[k] = num(x.get('Precio'))
    for x in r10:
        if es_cambio(x['Documento']) or NO_MERCA.search(x['Producto']):
            continue
        k = (norm_cli(x['Cliente']), norm_prod(x['Producto']))
        fac[k] = fac.get(k, 0.0) + num(x.get('Cantidad'))
        nombre.setdefault(k, (x['Cliente'].strip(), x['Producto'].strip()))
    en_r5 = {(norm_cli(x['Cliente']), norm_prod(x['Producto'])) for x in r5} if r5 else set()
    cl = dict(igual=0, sin_factura=[], parcial=[], de_mas=[], factura_sin_pedido=[])
    for k in set(ped) | set(fac):
        p, f = ped.get(k, 0.0), fac.get(k, 0.0)
        fila = dict(cliente=nombre[k][0], producto=nombre[k][1], pedido=round(p, 2), facturado=round(f, 2), gap=round(p - f, 2), usd=round((p - f) * usd.get(k, 0.0), 2), en_r5=k in en_r5)
        if abs(p - f) < 0.01:
            cl['igual'] += 1
        elif k not in ped:
            cl['factura_sin_pedido'].append(fila)
        elif f <= 0:
            cl['sin_factura'].append(fila)
        elif f < p:
            cl['parcial'].append(fila)
        else:
            cl['de_mas'].append(fila)
    fuera_r5 = [x for x in cl['sin_factura'] + cl['parcial'] if not x['en_r5']]
    pend_sin_gap = sum(1 for k in en_r5 if ped.get(k, 0.0) - fac.get(k, 0.0) <= 0)
    return dict(pares=len(set(ped) | set(fac)), iguales=cl['igual'], pedido_sin_factura=len(cl['sin_factura']), parcial=len(cl['parcial']), facturado_de_mas=len(cl['de_mas']), factura_sin_pedido=len(cl['factura_sin_pedido']),
                pendientes_fuera_de_r5=len(fuera_r5), r5_sin_gap=pend_sin_gap, usd_pedido_sin_facturar=round(sum(x['usd'] for x in cl['sin_factura'] + cl['parcial'] if x['usd'] > 0), 2),
                ej_sin_factura=top(cl['sin_factura'], 'usd'), ej_parcial=top(cl['parcial'], 'usd'), ej_de_mas=top(cl['de_mas'], 'gap'), ej_factura_sin_pedido=top(cl['factura_sin_pedido'], 'gap'))


def cruce_nombres(ts):
    vs = {}
    for c, t in ts.items():
        for x in t or []:
            n = (x.get('Cliente') or '').strip()
            if n:
                vs.setdefault(norm_cli(n), {}).setdefault(n, set()).add(c)
    mismas = [dict(nombres=sorted(g), n=len(g)) for g in vs.values() if len(g) > 1]
    claves = sorted(k for k in vs if len(k) >= 8)
    pares = []
    for i, a in enumerate(claves):
        for b in claves[i + 1:]:
            if abs(len(a) - len(b)) > 4 or a == b:
                continue
            s = difflib.SequenceMatcher(None, a, b)
            if s.real_quick_ratio() >= .9 and s.quick_ratio() >= .9 and s.ratio() >= .9:
                pares.append(dict(a=sorted(vs[a])[0], b=sorted(vs[b])[0], parecido=round(s.ratio(), 2)))
    pares.sort(key=lambda x: -x['parecido'])
    return dict(clientes=len(vs), misma_razon_distinta_escritura=len(mismas), ej_escritura=mismas[:MAX_EJ], posibles_renombrados=len(pares), ej_renombrados=pares[:12])


def cruce_marca(r10):
    sm = {}
    tot = 0
    for x in r10:
        if es_cambio(x['Documento']) or NO_MERCA.search(x['Producto']):
            continue
        tot += 1
        if not x.get('Marca', '').strip():
            p = x['Producto'].strip()
            sm[p] = sm.get(p, 0) + 1
    return dict(renglones_mercaderia=tot, renglones_sin_marca=sum(sm.values()), productos_sin_marca=len(sm), ej=[dict(producto=p, renglones=n) for p, n in sorted(sm.items(), key=lambda z: -z[1])[:8]])


def cruce_fecha_r8(r8, meta, hoy):
    cols = ['Fecha pedidos de venta s/f', 'Fecha facturas de venta s/r', 'Fecha en producción', 'Fecha en tránsito']
    u = {}
    for c in cols:
        ds = [d for d in (fecha(x.get(c)) for x in r8) if d]
        u[c] = max(ds).isoformat() if ds else None
    corte = meta.get('corte')
    return dict(corte_registrado=corte, dias_desde_corte=(hoy - D.date.fromisoformat(corte)).days if corte else None, r8_trae_fecha_de_stock=False, ultima_fecha_movimiento=u)


def medir(base, hoy):
    ts = {c: tabla(base, c) for c in ('R4', 'R5', 'R8', 'R10', 'R12', 'R13')}
    falta = [c for c, t in ts.items() if t is None]
    if falta:
        return dict(error='faltan ' + ', '.join(falta))
    meta = json.load(open(os.path.join(base, 'R8.json'), encoding='utf-8')) if os.path.exists(os.path.join(base, 'R8.json')) else {}
    return dict(r10_r4=cruce_r10_r4(ts['R10'], ts['R4']), r10_pte_r13=cruce_pte_r13(ts['R10'], ts['R13'], ts['R8']), r12_r10=cruce_r12_r10(ts['R12'], ts['R10'], ts['R5']),
                nombres=cruce_nombres({c: ts[c] for c in ('R4', 'R5', 'R10', 'R12', 'R13')}), marca=cruce_marca(ts['R10']), fecha_r8=cruce_fecha_r8(ts['R8'], meta, hoy),
                r8_r5=dict(pedidos_sf_r8=round(sum(num(x.get('Pedidos de venta s/f')) for x in ts['R8']), 2), cantidad_r5=round(sum(num(x.get('Cantidad')) for x in ts['R5']), 2)))


def todo(base, hoy):
    ms = metas(base)
    res, cruces = [], []
    tablas = {}
    for c in sorted(ms, key=orden):
        ruta = os.path.join(base, c + '.csv')
        if not os.path.exists(ruta):
            cruces.append(f'{c}: registrado sin archivo')
            continue
        s = auditar_reporte(ruta, base, hoy, nombre=f'Reporte_{c[1:]}.csv', contra_base=False)
        if s.get('meta'):
            if ms[c].get('filas') != s['meta']['filas']:
                s['graves'].append(f"Registro dice {ms[c].get('filas')} filas y el archivo trae {s['meta']['filas']}")
            if ms[c].get('bytes') != s['meta']['bytes']:
                s['graves'].append(f"Registro dice {ms[c].get('bytes')} bytes y el archivo pesa {s['meta']['bytes']}")
        cerrar(s)
        tablas[c] = s
        res.append(dict(reporte=c, veredicto=s['veredicto'], graves=s['graves'], avisos=s['avisos'], filas=s.get('meta', {}).get('filas'), hasta=s.get('meta', {}).get('hasta'), repetidas=s.get('meta', {}).get('duplicadas'), nc_positivas=s.get('meta', {}).get('nc_cantidad_positiva')))
    def filas(c):
        return tablas.get(c, {}).get('meta', {}).get('filas')
    if filas('R10') is not None and filas('R11') is not None and filas('R10') != filas('R11'):
        cruces.append(f"R10 ({filas('R10')}) y R11 ({filas('R11')}) deberían tener las mismas filas")
    if filas('R4') is not None and filas('R15') is not None and filas('R4') != filas('R15'):
        cruces.append(f"R4 ({filas('R4')}) y R15 ({filas('R15')}) deberían tener las mismas filas")
    cortes = {ms[c].get('corte') for c in tablas}
    if len(cortes) > 1:
        cruces.append('Reportes con distinto corte: ' + ', '.join(sorted(str(x) for x in cortes)))
    return dict(reportes=res, cruces=cruces, medicion=medir(base, hoy), veredicto='NO_SUBIR' if any(x['graves'] for x in res) else 'AVISOS' if cruces or any(x['avisos'] for x in res) else 'OK')


def main(a):
    if len(a) >= 3 and a[0] == 'archivo':
        hoy = D.date.fromisoformat(a[3]) if len(a) > 3 else D.date.today()
        out = auditar(a[1], a[2], hoy)
    elif len(a) >= 2 and a[0] == 'todo':
        hoy = D.date.fromisoformat(a[2]) if len(a) > 2 else D.date.today()
        out = todo(a[1], hoy)
    else:
        print(__doc__)
        return 2
    print(json.dumps(out, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
