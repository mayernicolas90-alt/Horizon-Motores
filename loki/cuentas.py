#!/usr/bin/env python3
"""cuentas.py 0.1 · motor Cuentas del datacenter (24/11/2026, DEC-1124a/b). Solo biblioteca estándar.

Dice, para cada cliente, si se trabaja o no y por qué, y une cada CUIT de Finnegans con su ficha del CRM.
Fuentes (todas en Turso):
  · regla D07 (k_regla): «no prospectar (…)», «otro vendedor (…)» y «X e Y son de Nicolás». Es la fuente que manda:
    si cambia la regla, cambia el resultado sin tocar código.
  · copia del CRM (crm_oportunidad): otro_vendedor, no_prospectar, cuenta_compartida, archivada, unificada_en
  · cuentas (quién lleva la cuenta, notas de Nicolás) · cliente_alias (razón social → CUIT)
  · limpia_comprobantes (los CUIT que compraron)
Escribe cue_cuentas: una fila por CUIT (o por ficha sin CUIT) con estado, trabajar (1/0), compartida, motivo, fuentes y conflicto.
Cuando dos fuentes se contradicen no decide: lo deja en «conflicto» para que lo defina Nicolás.

Uso (python3 -I): cuentas.py --contrato · cuentas.py --autotest · cuentas.py correr [--loki ruta] · cuentas.py simular
"""
import importlib.util, json, os, re, sys, unicodedata

VERSION = 'cuentas 0.2 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
CONTRATO = {'id': 'cuentas', 'nombre': 'Cuentas', 'disparo': 'loki',
            'lee': ['k_regla', 'crm_oportunidad', 'cuentas', 'cliente_alias', 'limpia_comprobantes'], 'escribe': ['cue_cuentas'],
            'que_hace': 'Qué cuentas se trabajan (D07 + CRM): otro vendedor, no prospectar, compartida, archivada; CUIT ↔ ficha; conflictos.'}
COLS = ['clave', 'cuit', 'crm_id', 'empresa', 'estado', 'trabajar', 'compartida', 'motivo', 'fuentes', 'conflicto']
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


def calcular(regla, oportunidades, cuentas, alias, compradores):
    """oportunidades: dicts de crm_oportunidad · cuentas: dicts {id, cuit, lleva} · alias: {alias_norm, cuit} · compradores: {cuit: razón social}."""
    R = leer_regla(regla)
    filas = {}
    def fila(clave, **k):
        f = filas.setdefault(clave, {'clave': clave, 'cuit': None, 'crm_id': None, 'empresa': '', 'marcas': [], 'fuentes': set()})
        for a, b in k.items():
            if b and not f.get(a):
                f[a] = b
        return f
    for o in oportunidades:
        c = dig(o.get('cuit'))
        f = fila(c or 'crm:' + o['id'], cuit=c or None, crm_id=o['id'], empresa=o.get('empresa') or '')
        f['fuentes'].add('crm')
        if str(o.get('otro_vendedor') or '0') not in ('0', ''):
            f['marcas'].append(('otro_vendedor', 'CRM: otro vendedor'))
        if str(o.get('no_prospectar') or '0') not in ('0', ''):
            f['marcas'].append(('no_prospectar', 'CRM: no prospectar'))
        if (o.get('cuenta_compartida') or '') == 'si':
            f['compartida'] = 1
        if o.get('unificada_en'):
            f['unificada_en'] = o['unificada_en']
        if str(o.get('archivada') or '0') not in ('0', ''):
            f['marcas'].append(('unificada' if o.get('unificada_en') else 'archivada',
                                'CRM: unificada en ' + o['unificada_en'] if o.get('unificada_en') else 'CRM: ficha archivada'))
    for k in cuentas:
        c = dig(k.get('cuit'))
        f = fila(c or 'crm:' + k['id'], cuit=c or None, crm_id=k['id'], empresa=k.get('empresa') or '')
        f['fuentes'].add('cuentas')
        f['lleva'] = k.get('lleva') or ''
        if re.search(r'otro vendedor', f['lleva'], re.I):
            f['marcas'].append(('otro_vendedor', 'cuentas: ' + f['lleva'][:60]))
    por_alias = {}
    for a in alias:
        por_alias.setdefault(dig(a.get('cuit')), a.get('alias'))
    for c, rs in compradores.items():
        f = fila(c, cuit=c, empresa=rs)
        f['fuentes'].add('finnegans')
        f.setdefault('razon_social', rs)
    for f in filas.values():
        nombres = ' | '.join(x for x in (f['empresa'], f.get('razon_social'), por_alias.get(f['cuit'] or '')) if x)
        for n in R['no_prospectar']:
            if coincide(n, nombres):
                f['marcas'].append(('no_prospectar', 'D07: no prospectar (' + n.strip() + ')'))
        for n in R['otro_vendedor']:
            if coincide(n, nombres):
                f['marcas'].append(('otro_vendedor', 'D07: otro vendedor (' + n.strip() + ')'))
        propia = any(coincide(n, nombres) for n in R['propias'])
        tipos = {m[0] for m in f['marcas']}
        conflicto = []
        if propia and tipos & {'otro_vendedor', 'no_prospectar'}:
            conflicto.append('D07 dice que es de Nicolás y ' + '; '.join(m[1] for m in f['marcas'] if m[0] in ('otro_vendedor', 'no_prospectar')))
            tipos -= {'otro_vendedor', 'no_prospectar'}
        if f.get('compartida') and re.search(r'no es conflicto|lo que se venda lo ganamos', f.get('lleva', ''), re.I):
            conflicto.append('CRM marca cuenta compartida y cuentas dice: ' + f['lleva'][:90])
        estado = next((e for e in ('otro_vendedor', 'no_prospectar', 'archivada', 'unificada') if e in tipos), 'trabajar')
        f['estado'] = estado
        f['trabajar'] = int(estado == 'trabajar')
        f['compartida'] = int(bool(f.get('compartida')))
        f['motivo'] = '; '.join(dict.fromkeys(m[1] for m in f['marcas'])) + ('; D07: es de Nicolás' if propia else '')
        f['fuentes'] = ','.join(sorted(f['fuentes']))
        f['conflicto'] = ' · '.join(conflicto) or None
    # 0.2: una ficha unificada es un duplicado: su CUIT compra y se trabaja como la ficha principal (24/11)
    por_crm = {f['crm_id']: f for f in filas.values() if f.get('crm_id')}
    for f in filas.values():
        if f['estado'] == 'unificada':
            p = por_crm.get(f.get('unificada_en'))
            f['trabajar'] = p['trabajar'] if p and p['estado'] != 'unificada' else 0
            f['motivo'] += f" · hereda de {f.get('unificada_en')}: {'se trabaja' if f['trabajar'] else 'no se trabaja'}"
    return [{k: f.get(k) for k in COLS} for f in sorted(filas.values(), key=lambda f: f['clave'])], R


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
    regla = q(db, "SELECT texto FROM k_regla WHERE id='D07'")
    comp = {}
    for r in q(db, "SELECT cuit, cliente FROM limpia_comprobantes WHERE cuit <> '' ORDER BY fecha"):
        comp[r['cuit']] = r['cliente'].strip()
    return ((regla[0]['texto'] if regla else ''), q(db, 'SELECT * FROM crm_oportunidad'), q(db, 'SELECT id, empresa, cuit, lleva FROM cuentas'),
            q(db, 'SELECT alias, cuit FROM cliente_alias'), comp)


def escribir(db, filas):
    db.run([('DROP TABLE IF EXISTS cue_cuentas', []), ('CREATE TABLE cue_cuentas(' + ', '.join(COLS) + ')', [])]
           + [('INSERT INTO cue_cuentas VALUES(' + ','.join('?' * len(COLS)) + ')', [f[c] for c in COLS]) for f in filas])


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
                                               archivada=0, unificada_en=None), **k)
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
        db = loki(a[a.index('--loki') + 1] if '--loki' in a else None).conectar()
        filas, R = calcular(*leer(db))
        if a[0] == 'correr':
            escribir(db, filas)
        db.close()
        if a[0] == 'simular':
            print(json.dumps([f for f in filas if f['estado'] != 'trabajar' or f['compartida'] or f['conflicto']], ensure_ascii=False))
        print('RESUMEN ' + json.dumps(resumen(filas, R), ensure_ascii=False))
        sys.exit(0)
    print(__doc__)
