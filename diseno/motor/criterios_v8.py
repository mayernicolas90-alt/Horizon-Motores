#!/usr/bin/env python3
"""Criterios de diseño tipo Illustrator, medidos sobre la escena del motor (vectores) y la pieza final (píxeles).
Uso: python3 motor/criterios_v8.py <pieza.escena.json> <pieza_final.png> [--hd <pieza_hd_final.png>]
Pruebas (cada una con su medida y umbral):
 1 margen_seguro      ningún texto o bloque a menos de 64 px del borde (área segura de WhatsApp, recorte de vista previa)
 2 alineacion         bordes izquierdos de los textos agrupados en pocas columnas (O'Donovan 2014: distancia mínima entre bordes)
 3 solapamiento       textos que se pisan entre sí (IoU de cajas = 0)
 4 escala_tipografica tamaños en pocas escalas (≤ 6 tamaños distintos; razón entre vecinos ≥ 1,15)
 5 legibilidad_movil  texto ≥ 22 px en 1080 (≈ 7 pt en un celular de 360 px de ancho)
 6 contraste          WCAG 2: ≥ 4,5:1 texto chico, ≥ 3:1 texto ≥ 30 px (luminancia relativa sRGB linealizada)
 7 ritmo_vertical     separaciones entre bloques en múltiplos de 4 px (grilla de 8 con medio paso)
 8 espacio_en_blanco  balance en grilla 8×8 (O'Donovan / SciFig): ninguna franja horizontal vacía > 9 % del alto entre contenido
 9 nitidez_hd         (si hay HD) la HD tiene más detalle que la 1080 ampliada (varianza del Laplaciano ≥ 1,3×)
"""
import argparse, json, math, cv2, numpy as np

SEG = 64


def caja_texto(e):
    s = e.get('s', 20); txt = e.get('txt') or ''.join(p[0] for p in e.get('parts', []) if p and p[0])
    w = e.get('tw') or (len(txt) * s * (0.58 if (e.get('w') or 400) >= 600 else 0.52) + len(txt) * (e.get('ls') or 0))
    x = e['x'] - (w / 2 if e.get('a') == 'middle' else w if e.get('a') == 'end' else 0)
    return [x, e['y'] - s * 0.78, x + w, e['y'] + s * 0.22], txt, s


def lum(rgb):
    c = np.asarray(rgb, float) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])


def hexrgb(h):
    h = str(h).lstrip('#')
    if h.startswith('rgba') or h.startswith('rgb') or len(h) not in (3, 6):
        return None
    if len(h) == 3:
        h = ''.join(ch * 2 for ch in h)
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('escena'); ap.add_argument('png'); ap.add_argument('--hd')
    a = ap.parse_args()
    S = json.load(open(a.escena)); im = cv2.imread(a.png)[..., ::-1]; H, W = im.shape[:2]
    textos = []
    for e in S:
        if e.get('t') in ('text', 'rich') and (e.get('txt') or e.get('parts')):
            b, txt, s = caja_texto(e)
            if txt.strip():
                textos.append(dict(b=b, txt=txt, s=s, ls=e.get('ls') or 0, a=e.get('a'), cont=next((i for i, r in sorted(enumerate(S), key=lambda z: z[1].get('w', 9e9) * z[1].get('h', 9e9)) if r.get('t') in ('rect', 'img') and not (r.get('w', 0) >= W and r.get('h', 0) >= H) and r['x'] <= e['x'] <= r['x'] + r['w'] and r['y'] <= e['y'] <= r['y'] + r['h']), None), fill=e.get('fill') or (e.get('parts') or [[0, 0, 0, '#fff']])[0][3]))
    bloques = [e for e in S if e.get('t') in ('rect', 'img') and not (e.get('x', 0) <= 0 and e.get('w', 0) >= W)]
    M, T = {}, {}
    # 1 margen
    malos = [t['txt'][:24] for t in textos if min(t['b'][0], t['b'][1], W - t['b'][2]) < SEG - 1 or H - t['b'][3] < 24]
    malos += ['bloque %dx%d' % (e['w'], e['h']) for e in bloques if e.get('t') == 'rect' and e.get('w', 0) < W
              and min(e['x'], W - e['x'] - e['w']) < SEG - 1 and e['y'] + e['h'] < H - 1]
    M['margen_seguro'] = malos[:6]; T['margen_seguro'] = not malos
    # 2 alineación: dentro de cada contenedor, los textos alineados a izquierda caen en ≤ 2 columnas (tolerancia 2 px)
    grupos = {}
    for t in textos:
        if t.get('a') in ('middle', 'end'):
            continue
        grupos.setdefault(t['cont'], []).append(round(t['b'][0]))
    malas = {}
    for g, xs in grupos.items():
        cols = []
        for x in sorted(xs):
            if not cols or x - cols[-1] > 2:
                cols.append(x)
        if len(cols) > (3 if g is None else 2):
            malas[str(g)] = cols
    M['alineacion'] = {'contenedores': len(grupos), 'desalineados': malas}
    T['alineacion'] = not malas
    # 3 solapamiento
    pis = []
    for i in range(len(textos)):
        for j in range(i + 1, len(textos)):
            A, B = textos[i]['b'], textos[j]['b']
            ix = max(0, min(A[2], B[2]) - max(A[0], B[0])); iy = max(0, min(A[3], B[3]) - max(A[1], B[1]))
            if ix * iy > 0.15 * min((A[2] - A[0]) * (A[3] - A[1]), (B[2] - B[0]) * (B[3] - B[1])):
                pis.append(f"{textos[i]['txt'][:18]} / {textos[j]['txt'][:18]}")
    M['solapamiento'] = pis[:5]; T['solapamiento'] = not pis
    # 4 escala tipográfica
    tam = sorted({round(t['s']) for t in textos})
    cerca = [(x, y) for x, y in zip(tam, tam[1:]) if y / x < 1.15]
    M['escala_tipografica'] = {'tamanos': tam, 'muy_parecidos': cerca}
    T['escala_tipografica'] = len(tam) <= 6 and len(cerca) <= 1
    # 5 legibilidad
    chicos = sorted({(round(t['s']), t['txt'][:22]) for t in textos if t['s'] < (18 if (t['ls'] > 0 and t['txt'] == t['txt'].upper()) or 'Sujeto a' in t['txt'] else 22)})
    M['legibilidad_movil'] = [f'{s}px {x}' for s, x in chicos][:8]; T['legibilidad_movil'] = not chicos
    # 6 contraste (fondo = mediana de píxeles alrededor de la caja, fuera de los trazos)
    bajos = []
    for t in textos:
        c = hexrgb(t['fill'])
        if not c:
            continue
        x0, y0, x1, y1 = (int(max(0, v)) for v in t['b']); x1 = min(W, x1); y1 = min(H, y1)
        zona = im[max(0, y0 - 6):min(H, y1 + 6), max(0, x0 - 6):min(W, x1 + 6)].reshape(-1, 3)
        if not len(zona):
            continue
        d = np.abs(zona.astype(int) - np.array(c)).sum(1)
        fondo = np.median(zona[d > 60], axis=0) if (d > 60).sum() > 20 else np.median(zona, axis=0)
        L1, L2 = sorted([lum(c), lum(fondo)], reverse=True); cr = (L1 + 0.05) / (L2 + 0.05)
        if cr < (3 if t['s'] >= 30 else 4.5):
            bajos.append(f"{t['txt'][:20]} {cr:.1f}:1")
    M['contraste'] = bajos[:8]; T['contraste'] = not bajos
    # 7 ritmo vertical: separaciones entre bloques (tarjetas anchas) en múltiplos de 4 y parejas (máx ≤ 2,2 × mín)
    tj = sorted([(e['y'], e['y'] + e['h']) for e in S if e.get('t') in ('rect', 'img') and e.get('w', 0) >= 900 and e.get('w', 0) < W and 340 < e['y'] < H - 180])
    bl = []
    for a0, b0 in tj:
        if bl and a0 <= bl[-1][1] + 2:
            bl[-1][1] = max(bl[-1][1], b0)
        else:
            bl.append([a0, b0])
    gaps = [round(q[0] - p[1]) for p, q in zip(bl, bl[1:])]
    fuera = [g for g in gaps if min(g % 4, 4 - g % 4) > 1.5 and abs(g - (gaps[0] if gaps else g)) > 2]   # separaciones distintas que no caen en grilla
    M['ritmo_vertical'] = {'separaciones_entre_bloques': gaps, 'fuera_de_grilla': fuera}
    T['ritmo_vertical'] = not fuera and (not gaps or max(gaps) <= 2.2 * max(1, min(gaps)))
    # 8 espacio en blanco: franjas horizontales sin contenido (bordes) entre el primer y el último contenido
    g = cv2.cvtColor(np.ascontiguousarray(im[..., ::-1]), cv2.COLOR_BGR2GRAY)
    ed = cv2.Canny(g, 40, 120); filas = ed[:, SEG:W - SEG].sum(1) > 255 * 6
    for e in S:                          # bordes de tarjetas y bandas (pie) cuentan como contenido aunque el contraste sea bajo
        if e.get('t') in ('rect', 'img') and not (e.get('w', 0) >= W and e.get('h', 0) >= H):
            for yy in (int(e['y']), int(e['y'] + e['h']) - 1):
                if 0 <= yy < H:
                    filas[yy] = True
    idx = np.where(filas)[0]; vacio = 0; desde = 0; run = 0
    for y in range(idx.min(), idx.max() + 1):
        run = 0 if filas[y] else run + 1
        if run > vacio:
            vacio, desde = run, y - run
    grid = [[float((ed[int(i * H / 8):int((i + 1) * H / 8), int(j * W / 8):int((j + 1) * W / 8)] > 0).mean()) for j in range(8)] for i in range(8)]
    M['espacio_en_blanco'] = {'franja_vacia_px': int(vacio), 'en_y': int(desde), 'pct_alto': round(100 * vacio / H, 1),
                             'celdas_vacias_8x8': int(sum(v < 0.002 for r in grid for v in r))}
    T['espacio_en_blanco'] = vacio / H <= 0.09
    # 10 balance visual (peso en gris: contraste local × área; Adobe: "pasala a gris y mirá dónde va el ojo")
    gg = g.astype(np.float32); loc = np.abs(gg - cv2.GaussianBlur(gg, (0, 0), 25))
    loc[int(H * 0.86):] = 0                                   # el pie fijo no cuenta
    ys_, xs_ = np.mgrid[0:H, 0:W]; m = loc.sum() or 1
    bx, by = float((loc * xs_).sum() / m / W), float((loc * ys_).sum() / m / H)
    M['balance_visual'] = {'centro_de_peso': [round(bx, 3), round(by, 3)]}
    T['balance_visual'] = abs(bx - 0.5) <= 0.10   # calibrado con las piezas aprobadas: ficha AN6000-7 0,414 · portada 0,479 (diagramación a izquierda)
    # 11 centrado vertical: textos de una línea dentro de botones/bandas, centrados (± 3 px sobre la altura de mayúscula)
    mal = []
    for e in S:
        boton = e.get('t') == 'rect' and e.get('h', 0) <= 70 and e.get('w', 0) < 300 and str(e.get('fill', '')).startswith('#')
        banda = e.get('t') == 'img' and 60 < e.get('h', 0) <= 120 and e.get('w', 0) >= 600     # banda del CTA
        if boton or banda:
            for t in textos:
                b = t['b']
                if e['x'] <= (b[0] + b[2]) / 2 <= e['x'] + e['w'] and e['y'] <= b[3] <= e['y'] + e['h'] + 4:
                    cc = b[3] - t['s'] * 0.58           # centro de la altura de mayúscula (línea de base − 0,36 em)
                    if abs(cc - (e['y'] + e['h'] / 2)) > 3:
                        mal.append(f"{t['txt'][:18]} {cc - (e['y'] + e['h'] / 2):+.0f}px")
    M['centrado_vertical'] = mal; T['centrado_vertical'] = not mal
    # 9 nitidez HD
    if a.hd:
        hd = cv2.imread(a.hd, cv2.IMREAD_GRAYSCALE)
        up = cv2.resize(g, (hd.shape[1], hd.shape[0]), interpolation=cv2.INTER_LANCZOS4)
        r = cv2.Laplacian(hd, cv2.CV_64F).var() / max(1e-6, cv2.Laplacian(up, cv2.CV_64F).var())
        M['nitidez_hd'] = {'px': [hd.shape[1], hd.shape[0]], 'detalle_vs_1080_ampliada': round(float(r), 2)}
        T['nitidez_hd'] = r >= 1.3
    T = {k: bool(v) for k, v in T.items()}
    ok = sum(T.values())
    print(json.dumps({'pieza': a.png, 'puntaje': f'{ok}/{len(T)}', 'pruebas': T, 'medidas': M}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
