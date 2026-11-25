#!/usr/bin/env python3
"""Ficha de pieza V8 desde la base del PM + verificador de promesas (sin IA).

  prods     -> motor/prods.json a partir de la exportación de productos del PM
  ficha     -> fichas/<pid>.json a partir del campo `pieza` de la ficha del PM
  verificar -> controla que cada cifra y cada tecnología de la pieza esté respaldada por la base

Uso:
  python3 ficha_v8.py prods     --pm <dir_pm> --salida motor/prods.json
  python3 ficha_v8.py ficha     --pm <dir_pm> --pid an6000-7 --salida fichas/an6000-7.json
  python3 ficha_v8.py verificar --pm <dir_pm> --ficha fichas/an6000-7.json

<dir_pm> = exportación ArtifactData de la base del PM (productos/*.json y config/*.json).
La pieza NO se renderiza si el verificador no da "aprobado": true.
"""
import argparse, glob, json, os, re, sys

TEC = ['GPON', 'XG-PON', 'XGS-PON', 'EPON', '10G EPON', 'P2P', 'Combo', 'C++', 'C+', 'B+',
       'WiFi 5', 'WiFi 6', 'WiFi 7', 'AX3000', 'HSCA', 'HU8A', 'PIBA', 'CIOA', 'MPLB', 'MPLA', 'PILA',
       'GPOA', 'GFOA', 'HSUD', 'POTS', 'USB', 'CATV', 'PoE', '10GE', '100GE', 'SFP+', 'QSFP28', 'MPLS']

def cargar(p):
    d = json.load(open(p, encoding='utf-8'))
    return d.get('data', d) if isinstance(d, dict) and isinstance(d.get('data'), dict) else d

def productos(dir_pm):
    out = {}
    for f in glob.glob(os.path.join(dir_pm, 'productos', '*.json')):
        out[os.path.basename(f)[:-5]] = cargar(f)
    return out

def reglas(dir_pm):
    f = os.path.join(dir_pm, 'config', 'reglas.json')
    if not os.path.exists(f):
        return {}
    r = cargar(f)
    return r.get('reglas', r)

def num(s):
    s = s.replace('−', '-')
    if re.fullmatch(r'\d{1,3}(\.\d{3})+', s):
        return s.replace('.', '')
    return s.replace(',', '.')

def numeros(txt):
    return {num(m) for m in re.findall(r'\d+(?:[.,]\d+)*', str(txt))}

def tecnologias(txt):
    t = ' ' + str(txt) + ' '
    hall = set()
    for k in sorted(TEC, key=len, reverse=True):
        if re.search(r'(?<![\w-])' + re.escape(k) + r'(?![\w+])', t, re.I):
            hall.add(k.upper())
            t = re.sub(re.escape(k), ' ', t, flags=re.I)
    return hall

def corpus(P, R, pid):
    f = P[pid]
    partes = [f.get('nombre'), f.get('resumen'), json.dumps(f.get('specs', []), ensure_ascii=False),
              json.dumps(f.get('ojo', []), ensure_ascii=False), json.dumps(f.get('argumentos', []), ensure_ascii=False),
              json.dumps(f.get('codigos', []), ensure_ascii=False)]
    for sku, v in (f.get('investigacion') or {}).items():
        for h in v.get('hechos', []):
            if h.get('estado') not in ('pendiente', 'contradictorio', 'no_aplica_al_sku', 'sin_correspondencia_BOM', 'no_demostrado'):
                partes.append(f"{h.get('campo')} {h.get('valor')}")
    for rid, r in R.items():
        if isinstance(r, dict) and r.get('ficha') == pid:
            partes.append(json.dumps(r, ensure_ascii=False))
    return ' '.join(str(p) for p in partes if p)

def medidas_mm(f):
    """Medidas reales del equipo desde las specs del PM (ej. "266 × 480 × 253,8 mm"): alto, ancho, prof."""
    for k, v in f.get('specs', []):
        if re.search(r'medida|f[ií]sico|dimensi', str(k), re.I):
            m = re.search(r'(\d+(?:[.,]\d+)?)\s*[×x]\s*(\d+(?:[.,]\d+)?)\s*[×x]\s*(\d+(?:[.,]\d+)?)\s*mm', str(v))
            if m:
                a, b, c = (float(x.replace(',', '.')) for x in m.groups())
                return {'alto': a, 'ancho': b, 'prof': c}
    return None

def textos_pieza(fz):
    out = [('titulo', fz.get('titulo', '')), ('chips', fz.get('chips', ''))]
    out += [('datos', f"{d.get('v')} {d.get('l')}") for d in fz.get('datos', [])]
    out += [('atr', a.get('t')) for a in fz.get('atr', [])]
    if fz.get('fuerte'):
        out.append(('fuerte', f"{fz['fuerte'].get('v')} {fz['fuerte'].get('l')}"))
    out += [('tabla', f"{t.get('l')}: {t.get('v')}") for t in fz.get('tabla', [])]
    out += [('modelos', f"{m.get('m')} {m.get('d', '')}") for m in fz.get('modelos', [])]
    return [(k, v) for k, v in out if v and str(v).strip()]

def verificar(P, R, fz):
    pid = fz.get('pid')
    if pid not in P:
        return {'aprobado': False, 'errores': [f'pid {pid} no existe en la base del PM']}
    base = corpus(P, R, pid)
    nb, tb = numeros(base), tecnologias(base)
    err, av = [], []
    prohib = list((P[pid].get('pieza') or {}).get('prohibido', []))
    for k, txt in textos_pieza(fz):
        for n in numeros(txt) - nb:
            if n not in {'1', '2', '3', '4'}:   # conteos chicos (2 HSCA, 1 ventilador) se validan por tecnología
                err.append(f'{k}: «{txt}» → la cifra {n} no está en la base')
        for t in tecnologias(txt) - tb:
            err.append(f'{k}: «{txt}» → {t} no figura en la base para este producto')
        for w in ('licencia', 'stock', 'entrega inmediata', 'garantía', 'garantia', 'homologad'):
            if w in str(txt).lower() and w not in base.lower():
                err.append(f'{k}: «{txt}» → «{w}» no tiene respaldo en la base para este producto')
        for p in prohib:
            if p.lower() in str(txt).lower():
                err.append(f'{k}: «{txt}» → promesa prohibida ({p})')
    # puertos PON prometidos contra lo que deja libre el kit (regla de configuración)
    for rid, r in R.items():
        if isinstance(r, dict) and r.get('ficha') == pid and r.get('tipo') == 'chasis' and r.get('puertos_por_placa'):
            maxp = (r['slots_servicio'] - r.get('slots_ocupados_por_kit', 0)) * r['puertos_por_placa']
            for k, txt in textos_pieza(fz):
                for m in re.finditer(r'(\d+)\s*(?:puertos\s*)?(?:x?gs?-?pon|gpon|pon)\b', str(txt), re.I):
                    if int(m.group(1)) > maxp:
                        err.append(f'{k}: «{txt}» → promete {m.group(1)} PON y el {r["nombre"]} de Horizon deja {maxp}')
    if len(fz.get('atr', [])) not in (0, 1, 3):
        av.append('atributos: usar 3 (grupo impar)')
    largos = [len(a.get('t', '')) for a in fz.get('atr', [])]
    if largos and max(largos) - min(largos) > 8:
        av.append('atributos con largos muy distintos: emparejar')
    if len(fz.get('datos', [])) > 4:
        av.append('más de 4 cifras: la plantilla muestra 4')
    return {'pid': pid, 'aprobado': not err, 'errores': err, 'avisos': av}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['prods', 'ficha', 'verificar'])
    ap.add_argument('--pm', required=True)
    ap.add_argument('--pid')
    ap.add_argument('--ficha')
    ap.add_argument('--salida')
    a = ap.parse_args()
    P, R = productos(a.pm), reglas(a.pm)
    if a.cmd == 'prods':
        lista = [dict({k: v for k, v in f.items() if k not in ('fotos', 'pieza')}, id=k) for k, f in sorted(P.items())]
        json.dump(lista, open(a.salida, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'prods.json: {len(lista)} fichas')
    elif a.cmd == 'ficha':
        f = P[a.pid]
        pz = dict(f.get('pieza') or {})
        if not pz:
            sys.exit(f'La ficha {a.pid} no tiene campo "pieza" en el PM: cargarlo antes.')
        def _px(x):
            m = re.match(r'(\d+)\s*[x×]\s*(\d+)', str(x.get('px', '')))
            return int(m.group(1)) * int(m.group(2)) if m else 0
        foto = max((x for x in f.get('fotos', []) if x.get('estado') == 'aprobada'), key=_px, default=None)
        if not foto:
            sys.exit(f'La ficha {a.pid} no tiene foto aprobada en el PM.')
        pz.pop('prohibido', None)
        if isinstance(pz.get('composicion'), dict) and 'medidas_mm' not in pz['composicion']:
            mm = medidas_mm(f)
            if mm:
                pz['composicion'] = dict(pz['composicion'], medidas_mm=mm)
        out = dict(pid=a.pid, foto=a.pid, **pz)
        json.dump(out, open(a.salida, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(json.dumps({'ficha': a.salida, 'foto_asset': foto['id'], 'bajar_a': f'fotos/{a.pid}.png'}, ensure_ascii=False))
    else:
        r = verificar(P, R, json.load(open(a.ficha, encoding='utf-8')))
        print(json.dumps(r, ensure_ascii=False, indent=1))
        sys.exit(0 if r['aprobado'] else 2)

if __name__ == '__main__':
    main()
