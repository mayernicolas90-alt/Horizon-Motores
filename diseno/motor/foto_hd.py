#!/usr/bin/env python3
"""Foto para HD (clásico, sin IA generativa): Lanczos + máscara de enfoque solo sobre el equipo.
Uso: python3 motor/foto_hd.py <entrada.png> <salida.png> --ancho_mostrado PX [--escala 2]
- Si la foto ya alcanza (px de origen >= px mostrados en HD), no se toca la geometría: solo enfoque suave.
- Si hay que ampliar: Lanczos4 hasta el tamaño HD (tope 2×) + máscara de enfoque con umbral (no realza ruido).
- Mantiene el alfa (bordes limpios: el alfa se reescala aparte y se recorta el halo).
- Informe: ampliación, nitidez (varianza del Laplaciano) antes/después, y aviso si la ampliación supera 1,8×.
Referencias: unsharp mask y varianza del Laplaciano (OpenCV), Lanczos (INTER_LANCZOS4).
"""
import argparse, json, cv2, numpy as np


def nitidez(rgb, alfa):
    g = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(g, cv2.CV_64F)
    m = alfa > 200
    return float(lap[m].var()) if m.any() else float(lap.var())


def enfocar(rgb, radio, cantidad, umbral):
    blur = cv2.GaussianBlur(rgb, (0, 0), radio)
    det = rgb.astype(np.float32) - blur.astype(np.float32)
    mask = (np.abs(det).max(axis=2, keepdims=True) > umbral).astype(np.float32)
    out = rgb.astype(np.float32) + cantidad * det * mask
    return np.clip(out, 0, 255).astype(np.uint8)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('entrada'); ap.add_argument('salida')
    ap.add_argument('--ancho_mostrado', type=float, required=True, help='px de ancho de la foto en la pieza 1080')
    ap.add_argument('--escala', type=float, default=2)
    a = ap.parse_args()
    im = cv2.imread(a.entrada, cv2.IMREAD_UNCHANGED)
    if im.shape[2] == 3:
        im = np.dstack([im, np.full(im.shape[:2], 255, np.uint8)])
    rgb, al = im[..., :3], im[..., 3]
    h, w = al.shape
    objetivo = a.ancho_mostrado * a.escala
    ampl = objetivo / w
    n0 = nitidez(rgb, al)
    if ampl > 1:
        f = min(ampl, 2.0)
        rgb = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_LANCZOS4)
        al = cv2.resize(al, None, fx=f, fy=f, interpolation=cv2.INTER_LANCZOS4)
        rgb = enfocar(rgb, radio=1.2 * f, cantidad=0.55, umbral=4)
    else:
        rgb = enfocar(rgb, radio=0.8, cantidad=0.25, umbral=3)
    al = np.where(al < 8, 0, al).astype(np.uint8)                   # sin halo de bordes casi transparentes
    cv2.imwrite(a.salida, np.dstack([rgb, al]))
    n1 = nitidez(rgb, al)
    rep = {'origen_px': [w, h], 'mostrado_hd_px': round(objetivo), 'ampliacion_hd': round(ampl, 2),
           'nitidez_antes': round(n0, 1), 'nitidez_despues': round(n1, 1),
           'aviso': ('foto chica para HD: pedir una de al menos %d px de ancho' % round(objetivo / 1.25)) if ampl > 1.8 else ''}
    print(json.dumps(rep, ensure_ascii=False))
