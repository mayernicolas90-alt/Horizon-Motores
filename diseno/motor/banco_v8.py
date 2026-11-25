#!/usr/bin/env python3
"""Banco de pruebas de la composición V8: OLT, dos ONT (una con foto chica) y un switch.
Usa la ficha de la AN6000-7 con composición y cambia la foto, la familia y las medidas.
Uso: python3 motor/banco_v8.py <salida> [--guardar]   (desde la carpeta del motor V8)
Compara contra motor/banco_esperado.json; --guardar lo reescribe con el resultado actual.
"""
import json, os, subprocess, sys

BASE = json.load(open('fichas/an6000-7_comp.json', encoding='utf-8'))
CASOS = [
    ('olt_an6000-7', 'an6000-7', 'olt', {'alto': 266, 'ancho': 480, 'prof': 253.8}),
    ('ont_hg6145f3', 'hg6145f3', 'ont', {'alto': 42, 'ancho': 135, 'prof': 185}),
    ('ont_hg6543d_foto_chica', 'ab611deea1ee9625e6a3f4fbf275727b', 'ont', {'alto': 42, 'ancho': 135, 'prof': 185}),
    ('switch_s5735l_sin_medidas', 'd94991ea7288c71b239f9502528fb953', 'olt', None),
]
CLAVES = ('mira', 'modo', 'foto', 'escala', 'calidad', 'sombra')

def correr(out):
    os.makedirs(out, exist_ok=True)
    res = {}
    for nombre, foto, fam, mm in CASOS:
        f = dict(BASE, foto=foto, formatos=['chat'])
        f['composicion'] = dict(BASE['composicion'], familia=fam, **({'medidas_mm': mm} if mm else {}))
        fp = os.path.join(out, nombre + '.json')
        json.dump(f, open(fp, 'w'), ensure_ascii=False)
        subprocess.run(['node', 'motor/render.js', fp, nombre, out], check=True, capture_output=True,
                       env=dict(os.environ, NODE_PATH=os.environ.get('NODE_PATH','')+':/opt/npm-tools/node_modules'))
        for k in ('portada', 'detalle'):
            png = os.path.join(out, f'{nombre}_chat_{k}.png')
            pan = json.loads(subprocess.run(['python3', 'motor/panal_v8.py', png, png.replace('.png', '_final.png'), 'ont' if fam == 'ont' else 'olt'],
                                            check=True, capture_output=True, text=True).stdout)
            c = json.load(open(png.replace('.png', '.composicion.json')))
            m = c['medidas']
            res[f'{nombre}/{k}'] = {'aprobado': c['aprobado'], 'pruebas': c['pruebas'], 'avisos': c['avisos'], 'panal': pan['aprobado'],
                                    **{x: m.get(x) for x in CLAVES}, 'luz': (m.get('luz') or {}).get('material'),
                                    'mirada': m.get('mirada'), 'par': c.get('par')}
    return res

if __name__ == '__main__':
    out = sys.argv[1]
    r = correr(out)
    json.dump(r, open(os.path.join(out, 'banco_resultado.json'), 'w'), ensure_ascii=False, indent=1)
    if '--guardar' in sys.argv:
        json.dump(r, open('motor/banco_esperado.json', 'w'), ensure_ascii=False, indent=1)
        print('esperado guardado')
    esp = json.load(open('motor/banco_esperado.json')) if os.path.exists('motor/banco_esperado.json') else {}
    mal = 0
    for k, v in r.items():
        ok = esp.get(k) == v
        mal += not ok
        print(('OK    ' if ok else 'CAMBIÓ'), k, '· aprobado' if v['aprobado'] else '· NO aprobado', '·', v['mira'], v['modo'],
              (v['escala'] or {}).get('modo'), 'ampl', (v['calidad'] or {}).get('ampliacion'), '·', ' | '.join(v['avisos'])[:160])
    print(f'{len(r) - mal} de {len(r)} piezas iguales al esperado')
    sys.exit(1 if mal else 0)
