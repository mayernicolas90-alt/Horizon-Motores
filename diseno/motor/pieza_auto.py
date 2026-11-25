#!/usr/bin/env python3
"""Borrador automático del campo `pieza` desde las specs del PM (sin IA, sin inventar).
Cada cifra y cada tecnología sale textual de las specs; después corre el verificador de ficha_v8.
Uso: python3 motor/pieza_auto.py --pm <dir_pm> --pid <id> [--salida pieza.json]
"""
import argparse, json, re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import ficha_v8 as F

# claves de specs preferidas por familia (regex sobre el nombre de la spec) y etiqueta corta
PRIO = {
    'olt': [(r'ONU', 'ONU por chasis'), (r'PON m', 'Puertos PON'), (r'Backplane', 'Backplane'), (r'Uplink', 'Uplinks'),
            (r'Alcance', 'Alcance PON'), (r'Medidas', 'Altura')],
    'ont': [(r'WiFi', 'WiFi'), (r'Puertos', 'Puertos'), (r'Energ', 'Consumo'), (r'Clientes', 'Clientes WiFi'), (r'Óptica', 'Óptica')],
    'empalme': [(r'Sellado', 'Sellado'), (r'Temperatura', 'Temperatura')],
    'switch': [(r'Capa 2', 'MAC'), (r'Ruteo', 'Rutas IPv4'), (r'24 puertos', '24 puertos'), (r'48 puertos', '48 puertos')],
}
CAT = {'olt': 'OLT', 'ont': 'ONT', 'switch': 'Switch', 'empalme': 'Caja de empalme', 'nap': 'Caja NAP', 'cable': 'Cable'}


def corto(v, n=14):
    """Primer tramo con cifra, corto, tal como está en la spec."""
    for seg in re.split(r'\s·\s|,\s|;\s', str(v)):
        seg = seg.strip()
        if re.search(r'\d', seg) and len(seg) <= n:
            return seg
    return None


def tramo(v, n=46):
    segs = [s.strip() for s in re.split(r'\s·\s', str(v)) if s.strip()]
    out = ''
    for s in segs:
        if len(out) + len(s) + 3 > n:
            break
        out = (out + ' · ' + s) if out else s
    if out or not segs:
        return out
    s0 = segs[0][:n]
    cut = max(s0.rfind(', '), s0.rfind(' '))
    return re.sub(r'\s+(con|de|en|y|o|a|para)$', '', s0[:cut].rstrip(' ,(')) if len(segs[0]) > n and cut > 10 else s0


def especial(fam, k, v):
    """Lecturas específicas que mejoran la etiqueta sin inventar."""
    if fam == 'ont' and re.search(r'Puertos', k):
        m = re.search(r'(\d+)\s*GE', v)
        if m:
            return f'{m.group(1)} GE', 'Puertos gigabit'
    if fam == 'ont' and re.search(r'WiFi', k):
        m = re.search(r'WiFi\s*\d', v)
        ax = re.search(r'AX\d{4}', v)
        if m:
            return (ax.group(0) if ax else m.group(0)), ('Doble banda' if 'banda' in v or 'GHz' in v else 'WiFi')
    if fam == 'ont' and re.search(r'Energ', k):
        m = re.search(r'(\d+(?:,\d+)?)\s*W\s*t[ií]pico', v)
        if m:
            return f'{m.group(1)} W', 'Consumo típico'
    if fam in ('empalme', 'nap') and re.search(r'Sellado', k):
        m = re.search(r'IP\d\d', v)
        if m:
            return m.group(0), 'Sellado'
    if re.search(r'Temperatura', k):
        m = re.search(r'-?\d+ a \+?\d+ °C', v)
        if m:
            return m.group(0), 'Temperatura'
    if re.search(r'Medidas', k):
        m = re.search(r'\((\d+U)', v)
        if m:
            return m.group(1), 'Altura en rack'
    return None


def borrador(P, pid):
    f = P[pid]
    fam = f.get('familia') or f.get('capa') or ''
    specs = [(str(k), str(v)) for k, v in f.get('specs', []) if not re.search(r'c[oó]mo leer', str(k), re.I)]
    datos, usadas = [], set()
    for rx, lab in PRIO.get(fam, []):
        for k, v in specs:
            if k in usadas or not re.search(rx, k, re.I):
                continue
            e = especial(fam, k, v)
            val, l = e if e else (corto(v), lab)
            if val:
                datos.append({'v': val, 'l': l}); usadas.add(k)
            break
        if len(datos) == 4:
            break
    fibras = [int(x) for x in re.findall(r'(\d+)\s*F\b', ' '.join(v for _, v in specs))]
    if fam in ('empalme', 'nap') and fibras:
        datos.insert(0, {'v': f'{max(fibras)} F', 'l': 'Fibras máx.'})
    for k, v in specs:                       # relleno genérico: specs con cifra corta
        if len(datos) >= 4:
            break
        if k in usadas:
            continue
        e = especial(fam, k, v)
        val, l = e if e else (corto(v), k)
        if val and len(l) <= 24:
            datos.append({'v': val, 'l': l}); usadas.add(k)
    txt = ' '.join(v for _, v in specs)
    tecs = [t for t in F.TEC if re.search(r'(?<![\w-])' + re.escape(t) + r'(?![\w+])', txt)]
    atr = [{'t': t, 'i': 'red'} for t in tecs if t not in ('Combo',) and not any(t in d['v'] for d in datos)][:3]
    for k, v in specs:                       # completar atributos con rasgos cortos sin cifra
        if len(atr) >= 3:
            break
        for seg in re.split(r'\s·\s', v):
            seg = seg.strip()
            if 6 <= len(seg) <= 20 and not re.search(r'\d', seg) and seg not in [a['t'] for a in atr]:
                atr.append({'t': seg[0].upper() + seg[1:], 'i': 'check'}); break
    tabla = [{'l': k, 'v': tramo(v)} for k, v in specs if k not in usadas][:5]
    modelo = (f.get('codigos') or [pid])[0]
    cat = CAT.get(fam, (f.get('nombre') or '').split(' ')[0])
    dv = {d['l']: d['v'] for d in datos}
    if fam == 'olt' and 'ONU por chasis' in dv and 'Puertos PON' in dv:
        titulo = f"OLT de {dv['ONU por chasis']} ONU y {dv['Puertos PON']} puertos PON"
    elif fam == 'ont' and datos:
        titulo = f"ONT GPON {datos[0]['v']}"      # corto: en la ONT el panal nace arriba a la izquierda y un título de 2 líneas lo tapa
    elif fam in ('empalme', 'nap') and 'Fibras máx.' in dv:
        titulo = f"{cat} {dv.get('Sellado', '')} hasta {dv['Fibras máx.']}".replace('  ', ' ')
    else:
        titulo = f"{cat} {modelo}"   # el modelo lo pone la plantilla debajo; sin repetir marca
    return {'titulo': titulo, 'chips': '', 'datos': datos, 'atr': atr, 'fuerte': datos[0] if datos else {},
            'tabla': tabla, 'modelos': [{'m': modelo, 'd': '', 'p': ''}],
            'familia_panal': 'olt' if fam in ('olt', 'switch') else ('ont' if fam == 'ont' else 'pasivo'),
            'prohibido': [], 'borrador': 'pieza_auto 0.1 · revisar y aprobar en el PM'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pm', required=True); ap.add_argument('--pid', required=True); ap.add_argument('--salida')
    a = ap.parse_args()
    P = F.productos(a.pm); R = F.reglas(a.pm)
    pz = borrador(P, a.pid)
    ficha = dict(pz, pid=a.pid, foto=a.pid)
    ver = F.verificar(P, R, ficha)
    out = {'pieza': pz, 'verificador': ver}
    if a.salida:
        json.dump(out, open(a.salida, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
