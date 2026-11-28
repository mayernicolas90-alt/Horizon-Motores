"""Banco de pruebas Fishtest 0.1 — ¿sirve cruzar lo que compró cada cliente con la jugada a proponer?

Backtest sin trampa (walk-forward): en cada fecha de corte T se mira SOLO lo vendido antes de T, se generan las
jugadas y se comprueba qué compró de verdad el cliente en los 180 días siguientes. Las reglas de complemento se
aprenden en cada corte con datos anteriores a T (nada del futuro).

Jugadas evaluadas
  REPOSICION   familia que el cliente ya compró 2+ veces (la vuelve a comprar)
  COMPLEMENTO  familia nueva sugerida por reglas A→B aprendidas antes de T (soporte ≥3, confianza ≥30 %, lift ≥1,5)
  OLT_ONU      compró OLT y nunca ONU → ONU (base instalada FiberHome)
Líneas de base (lo que haría cualquiera sin motor)
  BASE_REPETIR  todas las familias que el cliente ya compró alguna vez (contra REPOSICION)
  BASE_POPULAR  las 3 familias más vendidas que el cliente no tiene (contra COMPLEMENTO y OLT_ONU)

Criterio fijado ANTES de correr (D14): una jugada SIRVE si tiene ≥30 casos, acierta más que su línea de base
(lift ≥1,5) y la diferencia es significativa (z de dos proporciones, p < 0,05). Con <30 casos: EN PRUEBA.

Uso: python3 -I banco_fishtest.py VENTAS.jsonl [--autotest]
VENTAS.jsonl = una fila JSON por línea del R10 (fecha, comprobante, cuit, familia, subfamilia, cantidad, total).
"""
import collections, itertools, json, math, sys
from datetime import date, timedelta

VERSION = '0.1'
HORIZONTE = 180
CORTES = ['2025-01-01', '2025-04-01', '2025-07-01', '2025-10-01', '2026-01-01', '2026-04-01', '2026-05-20']
MIN_CASOS, LIFT_MIN, P_MAX = 30, 1.5, 0.05


def familia(r):
    f, s = (r.get('familia') or '').strip(), (r.get('subfamilia') or '').strip()
    return f'{f} / {s}' if f else None   # sin familia = diferencia de cambio, descuentos, anticipos: no es producto


def eventos(filas):
    """(cuit, familia) → {fecha: cantidad neta del día}. Las NC (cantidad negativa) netean la compra (D06)."""
    ev = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in filas:
        fam = familia(r)
        if fam and r.get('cuit'):
            ev[(r['cuit'], fam)][date.fromisoformat(r['fecha'][:10])] += float(r.get('cantidad') or 0)
    return ev


def compras(ev, desde, hasta):
    """cuit → {familia: nº de días con compra neta > 0} en [desde, hasta). Lo anulado por NC en la ventana no cuenta."""
    out = collections.defaultdict(dict)
    for (c, fam), dias in ev.items():
        neto = sum(q for d, q in dias.items() if desde <= d < hasta)
        if neto > 0:
            out[c][fam] = sum(1 for d, q in dias.items() if desde <= d < hasta and q > 0)
    return out


def reglas(hist):
    """A→B aprendidas solo con la historia: soporte ≥3 clientes, confianza ≥30 %, lift ≥1,5."""
    n = len(hist)
    cnt = collections.Counter(f for v in hist.values() for f in v)
    par = collections.Counter(p for v in hist.values() for p in itertools.permutations(v, 2))
    out = collections.defaultdict(list)
    for (a, b), k in par.items():
        conf = k / cnt[a]
        lift = conf / (cnt[b] / n)
        if k >= 3 and conf >= 0.30 and lift >= LIFT_MIN:
            out[a].append(b)
    return out


def es_olt(f): return '/ OLT' in f
def es_onu(f): return '/ ONU' in f or '/ ONT' in f


def jugadas(hist):
    """cuit → [(tipo, familia)] con lo que se sabía antes del corte."""
    r = reglas(hist)
    pop = [f for f, _ in collections.Counter(f for v in hist.values() for f in v).most_common()]
    out = {}
    for c, v in hist.items():
        j = set()
        for f, k in v.items():
            j.add(('BASE_REPETIR', f))
            if k >= 2:
                j.add(('REPOSICION', f))
            for b in r.get(f, []):
                if b not in v:
                    j.add(('COMPLEMENTO', b))
        if any(es_olt(f) for f in v) and not any(es_onu(f) for f in v):
            for f in pop:
                if es_onu(f):
                    j.add(('OLT_ONU', f)); break
        for f in [f for f in pop if f not in v][:3]:
            j.add(('BASE_POPULAR', f))
        out[c] = j
    return out


def z_test(a1, n1, a2, n2):
    """p bilateral de la diferencia de dos proporciones."""
    if not n1 or not n2:
        return 1.0
    p = (a1 + a2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) if 0 < p < 1 else 0
    if not se:
        return 1.0
    z = (a1 / n1 - a2 / n2) / se
    return math.erfc(abs(z) / math.sqrt(2))


def correr(filas, cortes=CORTES):
    ev = eventos(filas)
    t0 = min(d for dias in ev.values() for d in dias)
    tot = collections.defaultdict(lambda: [0, 0])          # tipo → [casos, aciertos]
    por_corte, ejemplos = [], collections.defaultdict(list)
    for t in cortes:
        T = date.fromisoformat(t)
        hist, fut = compras(ev, t0, T), compras(ev, T, T + timedelta(days=HORIZONTE))
        fila = {'corte': t, 'clientes': len(hist)}
        for c, js in jugadas(hist).items():
            for tipo, f in js:
                ok = f in fut.get(c, {})
                tot[tipo][0] += 1; tot[tipo][1] += ok
                fila[tipo] = fila.get(tipo, 0) + ok
                if ok and tipo in ('COMPLEMENTO', 'OLT_ONU') and len(ejemplos[tipo]) < 5:
                    ejemplos[tipo].append(f'{t} · …{c[-5:]} · {f}')
        por_corte.append(fila)
    return tot, por_corte, ejemplos


def veredicto(tot):
    res = {}
    for tipo, base in (('REPOSICION', 'BASE_REPETIR'), ('COMPLEMENTO', 'BASE_POPULAR'), ('OLT_ONU', 'BASE_POPULAR')):
        n, a = tot.get(tipo, [0, 0]); nb, ab = tot.get(base, [0, 0])
        pj, pb = (a / n if n else 0), (ab / nb if nb else 0)
        lift = pj / pb if pb else 0
        p = z_test(a, n, ab, nb)
        v = 'EN PRUEBA' if n < MIN_CASOS else ('SIRVE' if lift >= LIFT_MIN and p < P_MAX else 'NO SIRVE')
        res[tipo] = dict(base=base, casos=n, aciertos=a, acierto=pj, acierto_base=pb, lift=lift, p=p, veredicto=v)
    return res


def autotest():
    """Caso sintético con respuesta conocida + control de que no se filtra el futuro."""
    f = []
    for i in range(12):   # 12 clientes compran DROP y, 60 días después, CONECTORES
        c = f'30-0000000{i:02d}-1'
        f += [dict(fecha='2024-06-01', cuit=c, familia='FIBRA OPTICA', subfamilia='DROP', cantidad=1),
              dict(fecha='2024-08-01', cuit=c, familia='ODN', subfamilia='CONECTORES', cantidad=1)]
    for i in range(6):    # 6 clientes con DROP en 2024 y CONECTORES recién en 2025 (después del corte)
        c = f'30-1111111{i:02d}-1'
        f += [dict(fecha='2024-06-01', cuit=c, familia='FIBRA OPTICA', subfamilia='DROP', cantidad=1),
              dict(fecha='2025-02-01', cuit=c, familia='ODN', subfamilia='CONECTORES', cantidad=1)]
    for i in range(20):   # ruido: compran solo SFP
        f.append(dict(fecha='2024-07-01', cuit=f'30-2222222{i:02d}-1', familia='CARRIER', subfamilia='SFP', cantidad=1))
    f.append(dict(fecha='2024-07-02', cuit='30-22222200-1', familia='CARRIER', subfamilia='SFP', cantidad=-1))  # NC
    tot, _, _ = correr(f, ['2025-01-01'])
    ev = eventos(f); h = compras(ev, date(2024, 1, 1), date(2025, 1, 1))
    chk = [('regla DROP→CONECTORES aprendida', 'ODN / CONECTORES' in reglas(h).get('FIBRA OPTICA / DROP', [])),
           ('6 aciertos de complemento', tot['COMPLEMENTO'] == [6, 6]),
           ('NC netea la compra', 'CARRIER / SFP' not in h.get('30-22222200-1', {})),
           ('sin futuro en la historia', all(f2 != 'ODN / CONECTORES' for c, v in h.items() if c.startswith('30-1111') for f2 in v))]
    for n, ok in chk:
        print(('PASA ' if ok else 'FALLA'), n)
    return all(ok for _, ok in chk)


def main(a):
    if '--autotest' in a:
        return 0 if autotest() else 1
    filas = [json.loads(x) for x in open(a[0]) if x.strip()]
    tot, por_corte, ej = correr(filas)
    print(f'FISHTEST banco {VERSION} · {len(filas)} líneas R10 · cortes {CORTES[0]}…{CORTES[-1]} · horizonte {HORIZONTE} días')
    print(f'Criterio: ≥{MIN_CASOS} casos, lift ≥{LIFT_MIN} contra la línea de base, p < {P_MAX}\n')
    for tipo, r in veredicto(tot).items():
        print(f"{tipo:12s} {r['veredicto']:9s} · {r['aciertos']}/{r['casos']} = {r['acierto']:.0%} "
              f"vs {r['base']} {r['acierto_base']:.0%} · lift {r['lift']:.1f} · p {r['p']:.3f}")
    print('\nPor corte (aciertos):')
    for f in por_corte:
        print('  ' + ' · '.join(f'{k} {v}' for k, v in f.items()))
    for tipo, xs in ej.items():
        print(f'\nEjemplos de acierto {tipo}:'); [print('  ' + x) for x in xs]
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
