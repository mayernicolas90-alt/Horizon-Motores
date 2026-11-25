#!/usr/bin/env python3
"""cuentas.py 0.3 · motor Cuentas del datacenter (24/11/2026, DEC-1124a/b). Solo biblioteca estándar.

Dice, para cada cliente, si se trabaja o no y por qué, y une cada CUIT de Finnegans con su ficha del CRM.
Fuentes (todas en Turso):
  · regla D07 (k_regla): «no prospectar (…)», «otro vendedor (…)» y «X e Y son de Nicolás». Es la fuente que manda:
    si cambia la regla, cambia el resultado sin tocar código.
  · copia del CRM (crm_oportunidad): otro_vendedor, no_prospectar, cuenta_compartida, archivada, unificada_en,
    cuitsAdicionales (en `extra`)
  · cuentas (quién lleva la cuenta, notas de Nicolás) · cliente_alias (razón social → CUIT)
  · ventas (razón social de Finnegans) y limpia_comprobantes (los CUIT que compraron)
Escribe (DEC-1124a, solo sus tablas):
  · cue_cuentas: una fila por cuenta (CUIT principal o ficha sin CUIT) con estado, trabajar (1/0), compartida, motivo,
    fuentes, conflicto y, desde 0.3, la ficha elegida (crm_id), razon, archivada y unificada_en.
  · cue_marca (0.3): todas las marcas de cada cuenta, una por fila, con su fuente (una cuenta puede tener varias).
  · cue_cuit (0.3): los CUIT de cada cuenta (principal y adicionales), con razón social, fichas, lleva y fuentes por CUIT.
  La vista `clientes` de loki_sql se arma sobre estas tres tablas (paso 3 del datacenter).
Cuando dos fuentes se contradicen no decide: lo deja en «conflicto» para que lo defina Nicolás.
0.3 (24/11, paso 3, hacelo de Nicolás): marcas en cue_marca (la unión de las fuentes, no una sola); «unificada» es marca
de una ficha: si la cuenta tiene una ficha viva, las fichas unificadas en ella no le pasan marcas (Punta Alta, Full Play,
r140); la unificada no hereda de sí misma; CUIT adicionales de la ficha (cuitsAdicionales) en cue_cuit; una ficha sin
CUIT propio toma el primer adicional (r140 → CUIT de Mónica Martínez), como hacía clientes.

Uso (python3 -I): cuentas.py --contrato · cuentas.py --autotest · cuentas.py correr [--loki ruta] · cuentas.py simular
"""
import importlib.util, json, os, re, sys, unicodedata

VERSION = 'cuentas 0.3 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
CONTRATO = {'id': 'cuentas', 'nombre': 'Cuentas', 'disparo': 'loki',
            'lee': ['k_regla', 'crm_oportunidad', 'cuentas', 'cliente_alias', 'limpia_comprobantes', 'ventas'],
            'escribe': ['cue_cuentas', 'cue_marca', 'cue_cuit'],
            'que_hace': 'Qué cuentas se trabajan (D07 + CRM): otro vendedor, no prospectar, compartida, archivada; CUIT ↔ ficha; conflictos.'}
COLS = ['clave', 'cuit', 'crm_id', 'empresa', 'estado', 'trabajar', 'compartida', 'motivo', 'fuentes', 'conflicto',
        'ficha', 'razon', 'archivada', 'unificada_en']
COLS_MARCA = ['clave', 'marca', 'valor', 'fuente']
COLS_CUIT = ['cuit', 'clave', 'tipo', 'razon', 'fichas', 'lleva', 'fuentes', 'armado']
# alias de nombres de la regla que no aparecen tal cual en la razón social
ALIAS = {'amma': ['asociacion mutual mercantil argentina'], 'tv music': ['tv music', 'tv 4 jujuy'], 'itelsa': ['itelsa', 'itel s a'],
         'generacion wifi': ['generacion wi fi', 'generacion wifi'], 'supercanal': ['supercanal', 'super canal']}


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return ' ' + re.sub(r'[^a-z0-9]+', ' ', s).strip() + ' '


def dig(s):
    return re.sub(r'\D', '', str(s or ''))


def leer_regla(texto):
    """Extrae de D07 las listas «no prospectar (…)», «otro vendedor (…)» y las cuentas declaradas propias («X e Y son de Nicolás»)."""
    t = texto or ''
    def lista(nombre):
        m = re.search(nombre + r'\s*\(([^)]*)\)', t, re.I)
        if not m:
            return []
        partes = re.split(r'[,/;]| y ', re.sub(r'\bpor ahora\b', '', m.group(1), flags=re.I))
        return [norm(p).strip() for p in partes if norm(p).strip()]
    propias = []
    m = re.search(r'([A-Z][\w\- ]+?) e ([A-Z][\w\- ]+?) son de Nicol', t)
    if m:
        propias = [norm(m.group(1)).strip(), norm(m.group(2)).strip()]
    return {'no_prospectar': lista('no prospectar'), 'otro_vendedor': lista('otro vendedor'), 'propias': propias}


def coincide(nombre, empresa):
    e = norm(empresa)
    return any(norm(a) in e for a in ALIAS.get(nombre, [nombre]))


def adicionales(o):
    """CUIT adicionales de una ficha (cuitsAdicionales, guardado en crm_oportunidad.extra): solo dígitos, en orden."""
    try:
        ex = json.loads(o.get('extra') or '{}') if isinstance(o.get('extra'), str) else (o.get('extra') or {})
    except ValueError:
        ex = {}
    out = []
    for x in ex.get('cuitsAdicionales') or [] if isinstance(ex.get('cuitsAdicionales'), list) else []:
        c = dig(x.get('cuit') if isinstance(x, dict) else x)
        if c and c not in out:
            out.append(c)
    return out


def calcular_todo(regla, oportunidades, cuentas, alias, compradores, ventas=(), armado=None):
    """oportunidades: dicts de crm_oportunidad · cuentas: dicts {id, empresa, cuit, lleva} · alias: {alias, cuit} ·
    compradores: {cuit: razón social} · ventas: [{cuit, cliente}] en el orden de clientes (razón social por CUIT).
    Devuelve dict(filas=cue_cuentas, marcas=cue_marca, cuits=cue_cuit, R=regla leída)."""
    R = leer_regla(regla)
    filas = {}
    def fila(clave, **k):
        f = filas.setdefault(clave, {'clave': clave, 'cuit': None, 'crm_id': None, 'empresa': '', 'marcas': [], 'fuentes': set(),
                                     'fichas_l': []})
        for a, b in k.items():
            if b and not f.get(a):
                f[a] = b
        return f
    si = lambda v: str(v or '0') not in ('0', '', 'None', 'no')
    refs, cuit_fuentes, pendientes = {}, {}, []
    def ref(c, fuente):
        if c:
            cuit_fuentes.setdefault(c, set()).add(fuente)
    for o in oportunidades:
        c, ads = dig(o.get('cuit')), adicionales(o)
        if not c and ads:                       # como clientes: sin CUIT propio, el primer adicional es el suyo (r140)
            c, ads = ads[0], ads[1:]
        ads = [a for a in ads if a != c]
        for x in ([c] if c else []) + ads:
            refs[x] = refs.get(x, 0) + 1
            ref(x, 'crm')
        clave = c or 'crm:' + o['id']
        f = fila(clave, cuit=c or None, empresa=o.get('empresa') or '')
        f['fuentes'].add('crm')
        f['fichas_l'].append(dict(id=o['id'], empresa=o.get('empresa') or '', archivada=si(o.get('archivada')),
                                  unificada_en=o.get('unificada_en') or None, otro=si(o.get('otro_vendedor')),
                                  nop=si(o.get('no_prospectar')), compartida=(o.get('cuenta_compartida') or '') == 'si'))
        pendientes += [(a, clave, o['id']) for a in ads]
    lleva_cuit, cuentas_rs = {}, {}
    clave_ficha = {x['id']: f['clave'] for f in filas.values() for x in f['fichas_l']}
    for k in cuentas:
        c = dig(k.get('cuit'))
        # 0.3: una nota de cuentas sin CUIT va a la cuenta de su ficha (r140 no queda dos veces)
        f = fila(c or clave_ficha.get(k['id']) or 'crm:' + k['id'], cuit=c or None, crm_id=k['id'], empresa=k.get('empresa') or '')
        f['fuentes'].add('cuentas')
        f['lleva'] = k.get('lleva') or ''
        if c:
            ref(c, 'cuentas'); lleva_cuit[c] = k.get('lleva'); cuentas_rs.setdefault(c, k.get('empresa'))
        if re.search(r'otro vendedor', f['lleva'], re.I):
            f['marcas'].append(('otro_vendedor', None, 'cuentas: ' + f['lleva'][:60]))
    ventas_rs = {}
    for v in ventas:
        c = dig(v.get('cuit'))
        if c:
            ventas_rs.setdefault(c, v.get('cliente')); ref(c, 'ventas')
    por_alias = {}
    for a in alias:
        por_alias.setdefault(dig(a.get('cuit')), a.get('alias'))
    for c, rs in compradores.items():
        f = fila(c, cuit=c, empresa=rs)
        f['fuentes'].add('finnegans')
        f.setdefault('razon_social', rs)
    # CUIT adicionales: los que no tienen cuenta propia se suman a la cuenta de su ficha; si ya tienen una, no se elige:
    # queda en conflicto (salvo que su única ficha esté unificada en esa misma cuenta, como Gomez Leandro → Disnet)
    adic = []
    for a, clave, fid in pendientes:
        g = filas.get(a)
        if g is None:
            adic.append((a, clave))
            continue
        destino = {x['id'] for x in filas[clave]['fichas_l']}
        if g['fichas_l'] and all(x['unificada_en'] in destino for x in g['fichas_l']):
            continue
        g.setdefault('conflictos_extra', []).append(f'el CUIT {a} figura como adicional de la ficha {fid} y tiene cuenta propia: unir o corregir')
    for f in filas.values():
        fl = f['fichas_l']
        vivas = [x for x in fl if not x['unificada_en']]
        base = vivas or fl                      # «unificada» es de la ficha: si hay una viva, las unificadas no marcan
        elegida = next((x for x in fl if not x['archivada'] and not x['unificada_en']), fl[0] if fl else None)
        for x in base:
            if x['otro']:
                f['marcas'].append(('otro_vendedor', None, f"CRM: otro vendedor ({x['id']})"))
            if x['nop']:
                f['marcas'].append(('no_prospectar', None, f"CRM: no prospectar ({x['id']})"))
        if any(x['compartida'] for x in fl):
            f['compartida'] = 1
        if elegida:
            f['crm_id'] = f['ficha'] = elegida['id']
            activa = not elegida['archivada'] and not elegida['unificada_en']
            f['archivada'] = 0 if activa else 1
            f['unificada_en'] = elegida['unificada_en']
            if elegida['unificada_en']:
                f['marcas'].append(('unificada', elegida['unificada_en'], f"CRM: unificada en {elegida['unificada_en']} ({elegida['id']})"))
            if not activa:
                f['marcas'].append(('archivada', None, f"CRM: ficha archivada ({elegida['id']})"))
        f['razon'] = (elegida['empresa'] if elegida else None) or ventas_rs.get(f['cuit'] or '') or cuentas_rs.get(f['cuit'] or '') or None
        nombres = ' | '.join(x for x in (f['empresa'], f.get('razon_social'), por_alias.get(f['cuit'] or '')) if x)
        for n in R['no_prospectar']:
            if coincide(n, nombres):
                f['marcas'].append(('no_prospectar', None, 'D07: no prospectar (' + n.strip() + ')'))
        for n in R['otro_vendedor']:
            if coincide(n, nombres):
                f['marcas'].append(('otro_vendedor', None, 'D07: otro vendedor (' + n.strip() + ')'))
        propia = any(coincide(n, nombres) for n in R['propias'])
        tipos = {m[0] for m in f['marcas']}
        conflicto = list(f.get('conflictos_extra') or [])
        if propia and tipos & {'otro_vendedor', 'no_prospectar'}:
            conflicto.append('D07 dice que es de Nicolás y ' + '; '.join(m[2] for m in f['marcas'] if m[0] in ('otro_vendedor', 'no_prospectar')))
            tipos -= {'otro_vendedor', 'no_prospectar'}
        if f.get('compartida') and re.search(r'no es conflicto|lo que se venda lo ganamos', f.get('lleva', ''), re.I):
            conflicto.append('CRM marca cuenta compartida y cuentas dice: ' + f['lleva'][:90])
        if 'unificada' in tipos:
            tipos.discard('archivada')           # una unificada también está «no activa»: manda «unificada»
        estado = next((e for e in ('otro_vendedor', 'no_prospectar', 'archivada', 'unificada') if e in tipos), 'trabajar')
        f['estado'] = estado
        f['trabajar'] = int(estado == 'trabajar')
        f['compartida'] = int(bool(f.get('compartida')))
        f['motivo'] = '; '.join(dict.fromkeys(m[2] for m in f['marcas'])) + ('; D07: es de Nicolás' if propia else '')
        f['fuentes'] = ','.join(sorted(f['fuentes']))
        f['conflicto'] = ' · '.join(conflicto) or None
        f['propia'] = propia
    # 0.2: una ficha unificada es un duplicado: se trabaja como la ficha principal · 0.3: nunca hereda de sí misma
    por_crm = {}
    for f in filas.values():
        for x in f['fichas_l']:
            por_crm.setdefault(x['id'], f)
    for f in filas.values():
        if f['estado'] == 'unificada':
            p = por_crm.get(f.get('unificada_en'))
            f['trabajar'] = p['trabajar'] if p and p is not f and p['estado'] != 'unificada' else 0
            f['motivo'] += f" · hereda de {f.get('unificada_en')}: {'se trabaja' if f['trabajar'] else 'no se trabaja'}"
    marcas = []
    for f in filas.values():
        vistas = set()
        for m, valor, fuente in f['marcas']:
            if (m, fuente) not in vistas:
                vistas.add((m, fuente)); marcas.append(dict(clave=f['clave'], marca=m, valor=valor, fuente=fuente))
    def por_cuit(c, clave, tipo, razon):
        return dict(cuit=c, clave=clave, tipo=tipo, razon=razon, fichas=refs.get(c, 0), lleva=lleva_cuit.get(c),
                    fuentes=','.join(sorted(cuit_fuentes.get(c, set()))) or None, armado=armado)
    cuits = [por_cuit(f['cuit'], f['clave'], 'principal', f['razon']) for f in filas.values() if f['cuit']]
    cuits += [por_cuit(a, clave, 'adicional', ventas_rs.get(a) or cuentas_rs.get(a)) for a, clave in adic]
    filas_out = [{k: f.get(k) for k in COLS} for f in sorted(filas.values(), key=lambda f: f['clave'])]
    return dict(filas=filas_out, marcas=sorted(marcas, key=lambda m: (m['clave'], m['marca'], m['fuente'])),
                cuits=sorted(cuits, key=lambda x: x['cuit']), R=R)


def calcular(regla, oportunidades, cuentas, alias, compradores, ventas=()):
    r = calcular_todo(regla, oportunidades, cuentas, alias, compradores, ventas)
    return r['filas'], r['R']


def loki(ruta=None):
    ruta = ruta or os.path.join(AQUI, 'loki_sql.py')
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def q(db, sql):
    cols, filas = db.run([(sql, [])])[0]
    return [dict(zip(cols, f)) for f in filas]


def leer(db):
    """Lee las fuentes. Una tabla que no existe (base nueva, autotest de loki_sql) cuenta como vacía."""
    def lq(sql):
        try:
            return q(db, sql)
        except Exception as e:  # noqa: BLE001
            if 'no such table' in str(e).lower():
                return []
            raise
    regla = lq("SELECT texto FROM k_regla WHERE id='D07'")
    comp = {}
    for r in lq("SELECT cuit, cliente FROM limpia_comprobantes WHERE cuit <> '' ORDER BY fecha"):
        comp[r['cuit']] = (r['cliente'] or '').strip()
    ventas = lq("SELECT cuit, MAX(cliente) cliente FROM ventas WHERE empresa LIKE 'HORIZON TRADING%' GROUP BY cuit, cliente")
    return ((regla[0]['texto'] if regla else ''), lq('SELECT * FROM crm_oportunidad'), lq('SELECT id, empresa, cuit, lleva FROM cuentas'),
            lq('SELECT alias, cuit FROM cliente_alias'), comp, ventas)


def sentencias(r):
    """Las tres tablas del motor, enteras (todo o nada si quien llama lo corre en una transacción)."""
    st = []
    for t, cols, filas in (('cue_cuentas', COLS, r['filas']), ('cue_marca', COLS_MARCA, r['marcas']), ('cue_cuit', COLS_CUIT, r['cuits'])):
        st += [(f'DROP TABLE IF EXISTS {t}', []), (f'CREATE TABLE {t}(' + ', '.join(cols) + ')', [])]
        st += [(f'INSERT INTO {t} VALUES(' + ','.join('?' * len(cols)) + ')', [f[c] for c in cols]) for f in filas]
    return st


def escribir(db, r, transaccion=None):
    st = sentencias(r)
    (transaccion or (lambda d, s: d.run(s)))(db, st)

def resumen(filas, R):
    est = {}
    for f in filas:
        est[f['estado']] = est.get(f['estado'], 0) + 1
    return {'cuentas': len(filas), 'por_estado': est, 'compartidas': sum(f['compartida'] for f in filas),
            'conflictos': sum(1 for f in filas if f['conflicto']), 'regla': {k: len(v) for k, v in R.items()}}


# ---------------------------------------------------------------- autotest (sin datos reales)
def autotest():
    d07 = ('no prospectar (ITSA/Pogliotti/AMMA, Obercom, Comworks); otro vendedor (Sion, FESACOM, SuperCanal por ahora). '
           'Swissnet e Iplus son de Nicolás. Fichas archivadas fuera.')
    O = lambda i, emp, cuit='', **k: dict(dict(id=i, empresa=emp, cuit=cuit, otro_vendedor=0, no_prospectar=0, cuenta_compartida=None,
                                               archivada=0, unificada_en=None, extra=None), **k)
    ops = [O('a', 'Cliente Bueno', '30-1'), O('b', 'Comworks SA', '30-2'), O('c', 'Vision Cable', '30-3'), O('d', 'SION', '30-4'),
           O('e', 'Swissnet', '30-5', no_prospectar=1), O('f', 'Nodo Net', '30-6', cuenta_compartida='si'),
           O('g', 'Internet Plus', '30-7', cuenta_compartida='si'), O('h', 'Vieja', '30-8', archivada=1, unificada_en='a'),
           O('i', 'Cerrada', '', archivada=1), O('j', 'TPP', '30-9')]
    cue = [dict(id='g', empresa='Internet Plus', cuit='30-7', lleva='ventas (NO es conflicto, «lo que se venda lo ganamos»)'),
           dict(id='j', empresa='TPP', cuit='30-9', lleva='OTRO VENDEDOR: no contactar')]
    filas, R = calcular(d07, ops, cue, [dict(alias='Asociacion Mutual Mercantil Argentina', cuit='30-10')],
                        {'301': 'Cliente Bueno', '3010': 'Asociación Mutual Mercantil Argentina', '3011': 'Super Canal S A', '3012': 'Sin Ficha SRL'})
    F = lambda clave: next(f for f in filas if f['clave'] == clave)
    casos = [
        ('la regla D07 se lee: listas y cuentas propias', len(R['no_prospectar']) == 5 and len(R['otro_vendedor']) == 3 and R['propias'] == ['swissnet', 'iplus']),
        ('cuenta normal: se trabaja', F('301')['estado'] == 'trabajar' and F('301')['trabajar'] == 1),
        ('no prospectar por la regla (Comworks)', F('302')['estado'] == 'no_prospectar'),
        ('palabra completa: «Vision» no es «Sion»', F('303')['estado'] == 'trabajar' and F('304')['estado'] == 'otro_vendedor'),
        ('alias de la regla: AMMA = Asociación Mutual Mercantil', F('3010')['estado'] == 'no_prospectar'),
        ('cliente de Finnegans sin ficha también se evalúa (SuperCanal)', F('3011')['estado'] == 'otro_vendedor' and F('3012')['estado'] == 'trabajar'),
        ('D07 «es de Nicolás» contra la marca del CRM: se trabaja y queda conflicto', F('305')['trabajar'] == 1 and 'D07 dice' in (F('305')['conflicto'] or '')),
        ('compartida se trabaja pero queda marcada', F('306')['compartida'] == 1 and F('306')['trabajar'] == 1 and not F('306')['conflicto']),
        ('compartida con nota «no es conflicto»: conflicto para definir', 'compartida' in (F('307')['conflicto'] or '')),
        ('ficha unificada o archivada: estado propio', F('308')['estado'] == 'unificada' and F('crm:i')['estado'] == 'archivada'),
        ('0.2: la unificada hereda «trabajar» de la principal; la archivada no se trabaja', F('308')['trabajar'] == 1 and F('crm:i')['trabajar'] == 0),
        ('«otro vendedor» escrito en cuentas cuenta', F('309')['estado'] == 'otro_vendedor'),
    ]
    # 0.3 (paso 3): varias marcas por cuenta, «unificada» de ficha, CUIT adicionales
    X = lambda ads: json.dumps({'cuitsAdicionales': ads})
    ops3 = [O('p1', 'Punta Alta', '30-50'), O('p2', 'Coop Punta Alta', '30-50', archivada=1, unificada_en='p1'),
            O('s1', 'SION', '30-51', archivada=1, otro_vendedor=1, no_prospectar=1),
            O('r1', 'Contratista', '', extra=X([{'cuit': '27-60', 'nombre': 'Mónica'}, {'cuit': '20-61'}])),
            O('m1', 'Mónica', '27-60', archivada=1, unificada_en='r1'),
            O('n1', 'Nodo', '30-62', extra=X([{'cuit': '30-63'}])), O('g1', 'Gomez', '20-64', archivada=1, unificada_en='d1'),
            O('d1', 'Disnet', '30-65', extra=X([{'cuit': '20-64'}]))]
    r3 = calcular_todo(d07, ops3, [], [], {'3063': 'Montevision'}, [dict(cuit='30-63', cliente='Montevision')])
    G = lambda clave: next(f for f in r3['filas'] if f['clave'] == clave)
    M = lambda clave: sorted({m['marca'] for m in r3['marcas'] if m['clave'] == clave})
    C = {c['cuit']: c for c in r3['cuits']}
    casos += [
        ('0.3: ficha viva + unificada en ella con el mismo CUIT: sin marca y se trabaja (Punta Alta)',
         M('3050') == [] and G('3050')['trabajar'] == 1 and G('3050')['ficha'] == 'p1'),
        ('0.3: una cuenta guarda todas sus marcas (Sion: otro vendedor, no prospectar, archivada)',
         M('3051') == ['archivada', 'no_prospectar', 'otro_vendedor']),
        ('0.3: sin CUIT propio toma el primer adicional y se une con la unificada (r140 / Mónica)',
         G('2760')['ficha'] == 'r1' and M('2760') == [] and G('2760')['trabajar'] == 1),
        ('0.3: el resto de los adicionales sin cuenta propia va a cue_cuit de esa cuenta (Ripoll)',
         C.get('2061', {}).get('clave') == '2760' and C['2061']['tipo'] == 'adicional'),
        ('0.3: adicional con cuenta propia de Finnegans: no se elige, queda en conflicto (Montevision)',
         '3063' not in [c['cuit'] for c in r3['cuits'] if c['tipo'] == 'adicional'] and 'adicional' in (G('3063')['conflicto'] or '')),
        ('0.3: adicional cuya única ficha está unificada en la cuenta: sin conflicto (Gomez → Disnet)',
         not G('2064')['conflicto'] and M('2064') == ['archivada', 'unificada'] and G('2064')['trabajar'] == 1),
        ('0.3: cada CUIT figura una sola vez en cue_cuit', len(r3['cuits']) == len({c['cuit'] for c in r3['cuits']})),
    ]
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    ok = sum(1 for _, x in casos if x)
    print(f'autotest cuentas: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    if '--contrato' in a:
        print(json.dumps(dict(CONTRATO, version=VERSION), ensure_ascii=False))
        sys.exit(0)
    if a[:1] in (['correr'], ['simular']):
        L = loki(a[a.index('--loki') + 1] if '--loki' in a else None)
        db = L.conectar()
        r = calcular_todo(*leer(db))
        filas, R = r['filas'], r['R']
        if a[0] == 'correr':
            escribir(db, r, L.transaccion)
        db.close()
        if a[0] == 'simular':
            print(json.dumps([f for f in filas if f['estado'] != 'trabajar' or f['compartida'] or f['conflicto']], ensure_ascii=False))
        print('RESUMEN ' + json.dumps(resumen(filas, R), ensure_ascii=False))
        sys.exit(0)
    print(__doc__)
