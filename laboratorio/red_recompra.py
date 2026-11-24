#!/usr/bin/env python3
"""red_recompra.py 0.2 · laboratorio (24/11/2026) · ¿quién compra en los próximos 30 días?

Experimento, no motor. La prueba hacia atrás solo lee Turso; «pronosticar» escribe únicamente su tabla nn_pronostico.
Arma "fotos" del pasado: en cada fecha de corte, para cada cliente que ya compró, calcula rasgos con lo que se sabía
hasta ese día y mira si compró en los 30 días siguientes. Con esas fotos entrena y compara:
  · referencia A: más días sin comprar primero (la que propone ChatGPT)
  · referencia B: compra más reciente primero
  · regla de ciclo: el más cerca de su próxima fecha estimada (como Recompra)
  · regresión logística (numpy)
  · red neuronal chica (rasgos → 16 → 8 → 1, numpy)
Separación temporal: entrena con cortes hasta FIN_TRAIN y evalúa con los cortes posteriores (nunca ve el futuro).
Métrica principal: aciertos en el top 10 por corte (lo que entra en la portada). También AUC.

Uso: python3 -I laboratorio/red_recompra.py [--loki ruta] [--json salida.json]   (prueba hacia atrás, no escribe)
     python3 -I laboratorio/red_recompra.py pronosticar [--hoy AAAA-MM-DD]       (guarda la lista de hoy en nn_pronostico)
Límite conocido: las NC se aplican con lo que se sabe hoy (no hay fecha de disponibilidad), así que la evaluación es
retrospectiva y algo optimista. El CRM no guarda historia de estados, por eso no entra al entrenamiento.
"""
import datetime as D, importlib.util, json, math, os, re, statistics, sys
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
VENTANA, AGRUPAR, PASO = 30, 15, 14
INICIO, FIN_TRAIN = D.date(2024, 7, 1), D.date(2025, 12, 31)
ONU = re.compile(r'\b(ont|onu)\b|hg6\d{3}|an5506|eg8\d{3}|hs8\d{3}', re.I)
INVERSION = re.compile(r'\bolt\b|placa|switch|an6000|an5516|ma5800|rectificador|chasis', re.I)
CABLE = re.compile(r'cable|drop|fibra|adss|bobina', re.I)
RASGOS = ['log_dias_ult', 'eventos_365', 'eventos_90', 'log_eventos_tot', 'tiene_ciclo', 'ratio_ciclo', 'dif_ciclo_norm',
          'mad_rel', 'antig_log', 'part_onu', 'part_cable', 'part_inv', 'log_unid_365', 'compro_onu_90', 'skus_365']


def loki(ruta):
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def leer(db):
    cols, filas = db.run([('SELECT cuit, fecha, producto, subfamilia, familia, cantidad_neta FROM limpia_compras_firmes '
                           'WHERE coalesce(otro_vendedor,0)=0 AND cantidad_neta > 0', [])])[0]
    compras = {}
    for cuit, f, prod, sub, fam, q in filas:
        txt = ' '.join(str(x or '') for x in (prod, sub, fam))
        tipo = 'onu' if ONU.search(txt) else 'inv' if INVERSION.search(txt) else 'cable' if CABLE.search(txt) else 'otro'
        compras.setdefault(cuit, []).append((D.date.fromisoformat(f[:10]), tipo, float(q or 0), prod))
    return compras


def eventos(fechas):
    ev = []
    for d in sorted(set(fechas)):
        if not ev or (d - ev[-1]).days >= AGRUPAR:
            ev.append(d)
    return ev


def rasgos(hist, corte):
    """hist: compras del cliente con fecha <= corte."""
    ev = eventos([h[0] for h in hist])
    dias_ult = (corte - ev[-1]).days
    inter = [(b - a).days for a, b in zip(ev, ev[1:])]
    ciclo = statistics.median(inter) if len(inter) >= 2 else None
    mad = statistics.median(abs(x - ciclo) for x in inter) if ciclo else None
    u365 = [h for h in hist if (corte - h[0]).days <= 365]
    tot = sum(h[2] for h in u365) or 1.0
    part = lambda t: sum(h[2] for h in u365 if h[1] == t) / tot
    return [math.log1p(dias_ult), sum(1 for e in ev if (corte - e).days <= 365), sum(1 for e in ev if (corte - e).days <= 90),
            math.log1p(len(ev)), 1.0 if ciclo else 0.0, (dias_ult / ciclo) if ciclo else 0.0,
            ((dias_ult - ciclo) / max(ciclo, 7)) if ciclo else 0.0, (mad / ciclo) if ciclo else 0.0,
            math.log1p((corte - ev[0]).days), part('onu'), part('cable'), part('inv'), math.log1p(sum(h[2] for h in u365)),
            1.0 if any(h[1] == 'onu' and (corte - h[0]).days <= 90 for h in hist) else 0.0,
            float(len({h[3] for h in u365}))], ciclo, ev[-1]


def fotos(compras, ultimo):
    filas = []
    corte = INICIO
    while corte + D.timedelta(days=VENTANA) <= ultimo:
        for cuit, cs in compras.items():
            hist = [c for c in cs if c[0] <= corte]
            if not hist:
                continue
            x, ciclo, ult = rasgos(hist, corte)
            y = 1 if any(corte < c[0] <= corte + D.timedelta(days=VENTANA) for c in cs) else 0
            prox = (ult + D.timedelta(days=round(ciclo))) if ciclo else None
            filas.append(dict(corte=corte, cuit=cuit, x=x, y=y, dias_ult=(corte - ult).days,
                              dist_prox=abs((prox - corte).days) if prox else 10 ** 6))
        corte += D.timedelta(days=PASO)
    return filas


# ------------------------------------------------------------------ modelos (numpy)
def estandarizar(Xtr, *otros):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    return [(Xtr - mu) / sd] + [(o - mu) / sd for o in otros]


def logistica(X, y, l2=1e-2, it=3000, lr=0.1):
    w, b = np.zeros(X.shape[1]), 0.0
    for _ in range(it):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = p - y
        w -= lr * (X.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return lambda Z: 1 / (1 + np.exp(-(Z @ w + b)))


def red(X, y, capas=(16, 8), l2=1e-3, epocas=400, lr=0.01, semilla=0):
    rng = np.random.default_rng(semilla)
    dims = [X.shape[1], *capas, 1]
    W = [rng.normal(0, math.sqrt(2 / a), (a, b)) for a, b in zip(dims, dims[1:])]
    B = [np.zeros(b) for b in dims[1:]]
    m = [np.zeros_like(w) for w in W] + [np.zeros_like(b) for b in B]
    v = [np.zeros_like(w) for w in W] + [np.zeros_like(b) for b in B]
    peso = np.where(y == 1, (len(y) - y.sum()) / max(y.sum(), 1), 1.0)  # balancea positivos
    peso = peso / peso.mean()
    t = 0

    def adelante(Z):
        acts = [Z]
        for i, (w, b) in enumerate(zip(W, B)):
            z = acts[-1] @ w + b
            acts.append(np.maximum(z, 0) if i < len(W) - 1 else 1 / (1 + np.exp(-z)))
        return acts

    for _ in range(epocas):
        for idx in np.array_split(rng.permutation(len(y)), max(1, len(y) // 256)):
            acts = adelante(X[idx])
            d = (acts[-1][:, 0] - y[idx]) * peso[idx]
            d = d[:, None] / len(idx)
            gW, gB = [], []
            for i in range(len(W) - 1, -1, -1):
                gW.insert(0, acts[i].T @ d + l2 * W[i])
                gB.insert(0, d.sum(0))
                if i:
                    d = (d @ W[i].T) * (acts[i] > 0)
            t += 1
            for j, (p, g) in enumerate(zip(W + B, gW + gB)):
                m[j] = 0.9 * m[j] + 0.1 * g
                v[j] = 0.999 * v[j] + 0.001 * g * g
                p -= lr * (m[j] / (1 - 0.9 ** t)) / (np.sqrt(v[j] / (1 - 0.999 ** t)) + 1e-8)
    return lambda Z: adelante(Z)[-1][:, 0]


def auc(p, y):
    o = np.argsort(p)
    r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float('nan')


def top10(filas, puntaje):
    """aciertos promedio en el top 10 de cada corte, y compradores totales del corte."""
    por = {}
    for f, s in zip(filas, puntaje):
        por.setdefault(f['corte'], []).append((s, f['cuit'], f['y']))
    ac, comp = [], []
    for c, xs in sorted(por.items()):
        xs.sort(key=lambda t: (-t[0], t[1]))
        ac.append(sum(y for _, _, y in xs[:10])); comp.append(sum(y for _, _, y in xs))
    return dict(aciertos_top10=round(float(np.mean(ac)), 2), compradores_por_corte=round(float(np.mean(comp)), 2),
                cortes=len(ac), precision_top10=round(float(np.mean(ac)) / 10, 3),
                cobertura=round(float(np.sum(ac)) / max(float(np.sum(comp)), 1), 3))


COLS_P = ['corte', 'cuit', 'politica', 'puesto', 'puntaje', 'dias_ult', 'ciclo', 'proxima', 'excluida', 'version', 'calculado']
TABLA_P = 'nn_pronostico'


def pronosticar(db, hoy):
    """Guarda la lista de hoy de cada política en nn_pronostico (tabla propia, DEC-1124a). Una corrida por día:
    si ya hay filas de ese corte y versión, se reemplazan. Se mide a los 30 días contra limpia_compras_firmes."""
    compras = leer(db)
    excl = {r[0] for r in db.run([('SELECT cuit FROM cue_cuentas WHERE trabajar = 0 AND cuit IS NOT NULL', [])])[0][1]}
    F = fotos(compras, max(c[0] for cs in compras.values() for c in cs))
    X = np.array([f['x'] for f in F]); y = np.array([f['y'] for f in F], float)
    H = []
    for cuit, cs in compras.items():
        hist = [c for c in cs if c[0] <= hoy]
        if hist:
            x, ciclo, ult = rasgos(hist, hoy)
            prox = (ult + D.timedelta(days=round(ciclo))) if ciclo else None
            H.append(dict(cuit=cuit, x=x, ciclo=ciclo, dias_ult=(hoy - ult).days, prox=prox))
    Xs, Xh = estandarizar(X, np.array([h['x'] for h in H]))
    pol = {'red_neuronal': np.mean([red(Xs, y, capas=(8,), l2=0.1, epocas=100, semilla=s)(Xh) for s in range(5)], 0),
           'regla_ciclo': -np.array([abs((h['prox'] - hoy).days) if h['prox'] else 10 ** 6 for h in H], float),
           'ref_reciente': -np.array([h['dias_ult'] for h in H], float)}
    ahora = D.datetime.now(D.timezone.utc).isoformat(timespec='seconds')
    filas = []
    for nombre, s in pol.items():
        orden = sorted(range(len(H)), key=lambda i: (-s[i], H[i]['cuit']))
        puesto = 0
        for i in orden:
            ex = H[i]['cuit'] in excl
            puesto += 0 if ex else 1
            filas.append([hoy.isoformat(), H[i]['cuit'], nombre, None if ex else puesto, float(s[i]), H[i]['dias_ult'],
                          H[i]['ciclo'], H[i]['prox'].isoformat() if H[i]['prox'] else None, int(ex), VERSION, ahora])
    db.run([(f'CREATE TABLE IF NOT EXISTS {TABLA_P}(' + ', '.join(COLS_P) + ')', []),
            (f'DELETE FROM {TABLA_P} WHERE corte = ? AND version = ?', [hoy.isoformat(), VERSION])]
           + [(f'INSERT INTO {TABLA_P} VALUES(' + ','.join('?' * len(COLS_P)) + ')', f) for f in filas])
    return dict(corte=hoy.isoformat(), clientes=len(H), excluidos=len(excl & {h['cuit'] for h in H}), filas=len(filas))


VERSION = 'red_recompra 0.2'


def main(a):
    ruta = a[a.index('--loki') + 1] if '--loki' in a else os.path.join(AQUI, '..', 'loki', 'loki_sql.py')
    db = loki(ruta).conectar()
    if a[:1] == ['pronosticar']:
        hoy = D.date.fromisoformat(a[a.index('--hoy') + 1]) if '--hoy' in a else D.datetime.now(D.timezone(D.timedelta(hours=-3))).date()
        r = pronosticar(db, hoy)
        db.close()
        print('RESUMEN ' + json.dumps(r, ensure_ascii=False))
        return
    compras = leer(db)
    db.close()
    ultimo = max(c[0] for cs in compras.values() for c in cs)
    F = fotos(compras, ultimo)
    tr = [f for f in F if f['corte'] <= FIN_TRAIN]
    te = [f for f in F if f['corte'] > FIN_TRAIN]
    Xtr, Xte = (np.array([f['x'] for f in s]) for s in (tr, te))
    ytr, yte = (np.array([f['y'] for f in s], float) for s in (tr, te))
    Xtr, Xte = estandarizar(Xtr, Xte)
    res = dict(datos=dict(clientes=len(compras), ultimo_dato=ultimo.isoformat(), fotos_train=len(tr), fotos_test=len(te),
                          positivos_train=int(ytr.sum()), positivos_test=int(yte.sum()),
                          cortes_test=f"{te[0]['corte']} a {te[-1]['corte']}" if te else None))
    modelos = {
        'ref_A_mas_dias_sin_comprar': np.array([f['dias_ult'] for f in te], float),
        'ref_B_compra_mas_reciente': -np.array([f['dias_ult'] for f in te], float),
        'regla_ciclo': -np.array([f['dist_prox'] for f in te], float),
    }
    lg = logistica(Xtr, ytr)
    modelos['logistica'] = lg(Xte)
    # configuración elegida en validación interna (entrena ≤ 30/06/2025, valida 2º semestre 2025), antes de mirar el test
    preds = [red(Xtr, ytr, capas=(8,), l2=0.1, epocas=100, semilla=s)(Xte) for s in range(5)]  # 5 semillas: más estable
    modelos['red_neuronal'] = np.mean(preds, 0)
    res['modelos'] = {k: dict(auc=round(auc(v, yte), 3), **top10(te, v)) for k, v in modelos.items()}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    if '--json' in a:
        json.dump(res, open(a[a.index('--json') + 1], 'w'), ensure_ascii=False, indent=1, default=str)


if __name__ == '__main__':
    main(sys.argv[1:])
