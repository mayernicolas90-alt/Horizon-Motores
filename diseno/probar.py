#!/usr/bin/env python3
"""Banco de pruebas del motor de diseño V9 (correr desde diseno/).
Uso: python3 probar.py --referencias <dir con AN6000-7_chat_portada.png y AN6000-7_chat_ficha.png>
Necesita: fotos en diseno/fotos/ (an6000-7.png, hg6145f3.png, ab611deea1ee9625e6a3f4fbf275727b.png,
d94991ea7288c71b239f9502528fb953.png, ont-hg6145f3.png, ont-hg6145f3_hd.png), Poppins instalada,
motor/prods.json (ficha_v8.py prods), Node con playwright y pdfjs-dist 4 en /opt/npm-tools/node_modules.
Pruebas: 1 regresión AN6000-7 píxel por píxel (sin pulido) · 2 banco de composición 8/8 · 3 pieza V9 de la
HG6145F3: composición aprobada, criterios 11/11 y nitidez HD. Salida 0 = PASA.
"""
import argparse, json, os, subprocess, sys
import cv2

AQUI = os.path.dirname(os.path.abspath(__file__))
ENV = dict(os.environ, NODE_PATH=os.environ.get('NODE_PATH', '') + ':/opt/npm-tools/node_modules')


def corre(cmd):
    return subprocess.run(cmd, cwd=AQUI, env=ENV, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--referencias', required=True); a = ap.parse_args()
    out = os.path.join(AQUI, 'salida'); os.makedirs(out, exist_ok=True)
    ok = True
    # 1 regresión
    corre(['node', 'motor/render.js', 'fichas/an6000-7.json', 'reg', out])
    for k, ref in (('portada', 'AN6000-7_chat_portada.png'), ('detalle', 'AN6000-7_chat_ficha.png')):
        corre([sys.executable, 'motor/panal_v8.py', f'{out}/reg_chat_{k}.png', f'{out}/reg_chat_{k}_final.png', 'olt'])
        x, y = cv2.imread(f'{out}/reg_chat_{k}_final.png'), cv2.imread(os.path.join(a.referencias, ref))
        dif = int((x != y).any(2).sum()) if x is not None and y is not None and x.shape == y.shape else -1
        print(('PASA ' if dif == 0 else 'FALLA'), f'· regresión AN6000-7 {k}: {dif} px distintos'); ok &= dif == 0
    # 2 banco
    r = corre([sys.executable, 'motor/banco_v8.py', os.path.join(out, 'banco')])
    fin = (r.stdout.strip().splitlines() or ['sin salida'])[-1]
    print(('PASA ' if r.returncode == 0 else 'FALLA'), '· banco de composición:', fin); ok &= r.returncode == 0
    # 3 pieza V9
    corre(['node', 'motor/render.js', 'fichas/ont-hg6145f3_v9.json', 'v9', out])
    for k in ('portada', 'detalle'):
        corre([sys.executable, 'motor/panal_v8.py', f'{out}/v9_chat_{k}.png', f'{out}/v9_chat_{k}_final.png', 'ont', f'{out}/v9_chat_{k}_hd.png'])
        c = json.load(open(f'{out}/v9_chat_{k}.composicion.json'))
        cr = json.loads(corre([sys.executable, 'motor/criterios_v8.py', f'{out}/v9_chat_{k}.escena.json', f'{out}/v9_chat_{k}_final.png',
                               '--hd', f'{out}/v9_chat_{k}_hd_final.png']).stdout)
        bien = c['aprobado'] and all(cr['pruebas'].values())
        print(('PASA ' if bien else 'FALLA'), f'· V9 HG6145F3 {k}: composición {c["aprobado"]} · criterios {cr["puntaje"]}'
              f' · nitidez HD {cr["medidas"]["nitidez_hd"]["detalle_vs_1080_ampliada"]}×'); ok &= bien
    print('\nRESULTADO:', 'PASA' if ok else 'FALLA')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
