#!/usr/bin/env python3
"""memoria_check.py v1.0.0 · control de memoria de Loki (Nicolás 15/11: «que no se pierda»).

Cruza lo que propone loki.py (urgentes.json, abrir.json) contra la memoria del Data Center
(cuentas/<id>.json) y la ficha del CRM (respaldo.json). Solo lee y calcula: no escribe nada.

Uso:
  python3 -I memoria_check.py DATOS AAAA-MM-DD          → informe al chat (texto) + DATOS/memoria.json
  python3 -I memoria_check.py --autotest                 → casos sanos y sabotajes

DATOS debe tener: urgentes.json, abrir.json, respaldo.json, R10.csv (opcional) y la carpeta
cuentas/ (ArtifactData list de `cuentas` con out_dir=DATOS).

Códigos por línea:
  AJUSTAR   la propuesta choca con la cuenta o la ficha: se muestra la acción corregida (manda la cuenta).
  AVISO     algo a mirar (seguimiento genérico en cuenta que no responde, marca de otra fuente que choca).
  BOX       cotización vencida: se muestra como aviso en el box; nunca como pregunta de estado ni perdida.
  OK        sin conflicto.
Además: SIN_REGLA (cuentas del top sin cuentas/<id>) y FACTURA_SIN_CARGAR (R10 contra CRM).
"""
import csv, json, os, re, sys, tempfile, unicodedata
from datetime import date, timedelta

VERSION = '1.0.0'
PRODUCTOS = {'onu': ('onu', 'ont', 'hg6145', 'hg6543', 'eg8'), 'drop': ('drop',), 'fibra': ('fibra', 'adss', 'cable'),
             'olt': ('olt', 'an6000', 'ma5800'), 'placa': ('placa', 'gphf', 'gpoa', 'gc8b'), 'switch': ('switch', 's5735', 's6730')}
GENERICAS = ('preguntar si la traba es precio o plazo', 'consultar si esta con algun requerimiento', 'retomar contacto')
VENDEDORES = ('nicolas mayer', 'ventas horizon')


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9/ ]', ' ', s)).strip()


def fecha_ddmm(txt, hoy):
    """Primera fecha dd/mm del texto como date (año de hoy; si quedó >300 días atrás, año siguiente)."""
    m = re.search(r'\b(\d{1,2})/(\d{1,2})\b', txt or '')
    if not m:
        return None
    try:
        f = date(hoy.year, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    if (hoy - f).days > 300:
        f = date(hoy.year + 1, f.month, f.day)
    return f


def productos_en(txt):
    t = norm(txt)
    return {p for p, ks in PRODUCTOS.items() if any(re.search(r'\b' + k, t) for k in ks)}


def cargar(datos):
    j = lambda n: json.load(open(os.path.join(datos, n), encoding='utf-8'))
    urg, abr = j('urgentes.json'), j('abrir.json')
    resp = j('respaldo.json')
    col = resp.get('collections', resp)
    opp, cot = col.get('oportunidades', {}), col.get('cotizaciones', {})
    if isinstance(opp, list):
        opp = {str(x.get('id')): x for x in opp}
    if isinstance(cot, list):
        cot = {str(x.get('id')): x for x in cot}
    cuentas = {}
    d = os.path.join(datos, 'cuentas')
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith('.json'):
                x = json.load(open(os.path.join(d, f), encoding='utf-8'))
                cuentas[f[:-5]] = x.get('data', x) if isinstance(x, dict) else x
    return urg, abr, opp, cot, cuentas


def resolver(item, opp, cot, cuentas):
    """id de oportunidad: por número de cotización, después por nombre (empresa/cliente/cuenta)."""
    ref = norm(item.get('ref') or item.get('n') or '')
    nom = norm(item.get('cuenta') or item.get('cliente') or '')
    if ref:
        for c in cot.values():
            if norm(c.get('numero')) == ref and c.get('oportunidadId') and (not nom or nom[:5] in norm(c.get('cliente'))):
                return c['oportunidadId']
    pal = [w for w in nom.split() if len(w) > 3 and w not in ('s r l', 'srl', 'sapem', 'sas')]
    mejores = []
    for i, o in opp.items():
        if o.get('archivada'):
            continue
        e = norm(o.get('empresa'))
        if not e:
            continue
        hits = sum(1 for w in pal if w in e)
        if hits:
            mejores.append((hits, i))
    for i, cta in cuentas.items():
        e = norm(cta.get('empresa'))
        hits = sum(1 for w in pal if w in e)
        if hits:
            mejores.append((hits + 0.5, i))
    if mejores:
        return sorted(mejores, reverse=True)[0][1]
    return None


def revisar(item, tipo_lista, hoy, opp, cot, cuentas):
    oid = resolver(item, opp, cot, cuentas)
    o = opp.get(oid, {}) if oid else {}
    cta = cuentas.get(oid) if oid else None
    accion = item.get('accion') or ''
    texto = ' '.join([accion, item.get('por_que') or '', item.get('tipo') or '', item.get('ref') or ''])
    res = dict(cuenta=item.get('cuenta') or item.get('cliente'), ref=item.get('ref') or item.get('n'), lista=tipo_lista,
               id=oid, codigos=[], motivos=[], accion_loki=accion, accion=accion, regla=bool(cta))
    if tipo_lista == 'vencidas':
        res['codigos'].append('BOX')
        res['motivos'].append(f"venció el {item.get('vence') or '?'}: aviso en el box; renovar o dar de baja lo decide Nicolás (nunca «perdida»)")
    # 1) fecha: la ficha o la cuenta fijan una próxima fecha posterior a hoy
    pf = None
    if o.get('proximaFecha'):
        try:
            pf = date.fromisoformat(str(o['proximaFecha'])[:10])
        except ValueError:
            pf = None
    if cta and cta.get('proxima'):
        fc = fecha_ddmm(cta['proxima'], hoy)
        if fc and (pf is None or fc > pf):
            pf = fc
    if pf and pf > hoy and tipo_lista == 'vencidas':
        res['motivos'].append(f'ficha: próxima {pf.strftime("%d/%m")} · {(o.get("proximaAccion") or "")[:140]}')
    if pf and pf > hoy and tipo_lista != 'vencidas':
        nueva = (cta or {}).get('proxima') or o.get('proximaAccion') or ''
        res['codigos'].append('AJUSTAR')
        res['motivos'].append(f'no es hoy: la ficha/cuenta fija {pf.strftime("%d/%m")}')
        res['accion'] = nueva[:220] or f'esperar al {pf.strftime("%d/%m")}'
    # 2) descarta: la propuesta ofrece algo que la cuenta descartó
    if cta:
        desc = ' '.join(cta.get('descarta') or [])
        choque = productos_en(texto) & productos_en(desc)
        if choque:
            emp = '; '.join(cta.get('empuja') or [])
            res['codigos'].append('AJUSTAR')
            res['motivos'].append(f"ofrece {', '.join(sorted(choque))} y la cuenta lo descarta ({desc[:120]})")
            res['accion'] = (f'empujar: {emp}' if emp else 'no ofrecer lo descartado')[:220]
        # 3) no insistir con seguimiento genérico
        noi = norm(' '.join(cta.get('noInsistir') or []))
        if 'generic' in noi and any(g in norm(accion) for g in GENERICAS):
            res['codigos'].append('AVISO')
            res['motivos'].append('la cuenta no responde a seguimientos genéricos: llevar un dato o una pregunta concreta')
        # 4) marcas de otra fuente que chocan con la cuenta
        for oj in item.get('ojo') or []:
            if 'no tocar' in norm(oj) and 'otro vendedor' not in norm(cta.get('lleva')):
                res['codigos'].append('AVISO')
                res['motivos'].append(f'«{oj[:60]}» choca con la cuenta (lleva: {str(cta.get("lleva"))[:40]}): manda la cuenta')
        if 'otro vendedor' in norm(cta.get('lleva')):
            res['codigos'].append('AJUSTAR')
            res['motivos'].append('la cuenta es de otro vendedor: no contactar')
            res['accion'] = 'no contactar (otro vendedor)'
    if not res['codigos']:
        res['codigos'].append('OK')
    return res


def facturas_sin_cargar(datos, hoy, opp, cot, dias=45):
    p = os.path.join(datos, 'R10.csv')
    if not os.path.exists(p):
        return None
    filas = list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'))
    desde = (hoy - timedelta(days=dias)).isoformat()
    fa, nc = {}, []
    for r in filas:
        if r.get('Empresa') != 'HORIZON TRADING S.A.' or (r.get('Fecha Comprobante') or '') < desde:
            continue
        doc, comp = norm(r.get('Documento')), r.get('Comprobante') or ''
        try:
            tot = float(r.get('Total') or 0)
        except ValueError:
            tot = 0.0
        if 'credito' in doc:
            nc.append((norm(r.get('Cliente')), round(-tot, 0), r.get('Fecha Comprobante') or ''))
        elif 'factura' in doc and norm(r.get('Vendedor')) in VENDEDORES:
            x = fa.setdefault(comp, dict(comp=comp, fecha=r['Fecha Comprobante'], cliente=r.get('Cliente'), tot=0.0, prod=r.get('Producto', '')[:40]))
            x['tot'] += tot
    base = json.dumps([cot, [o.get('historial') for o in opp.values()]], ensure_ascii=False)
    anuladas = set()
    for cli, tot, fnc in nc:  # cada NC anula UNA factura: la más reciente anterior, mismo cliente y total
        cand = [c for c, x in fa.items() if c not in anuladas and norm(x['cliente']) == cli
                and round(x['tot'], 0) == tot and x['fecha'] <= fnc]
        if cand:
            anuladas.add(max(cand, key=lambda c: fa[c]['fecha']))
    out = []
    for comp, x in sorted(fa.items(), key=lambda k: k[1]['fecha']):
        if comp in anuladas:
            continue  # anulada con nota de crédito
        num = comp.split('-')[-1].lstrip('0')
        if num and re.search(r'(?<!\d)0*' + num + r'(?!\d)', base):
            continue
        out.append(x)
    return out


def correr(datos, hoy_s):
    hoy = date.fromisoformat(hoy_s)
    urg, abr, opp, cot, cuentas = cargar(datos)
    items = [(i, 'top5') for i in urg.get('top5', [])] + [(i, 'siguen') for i in urg.get('siguen', [])]
    items += [(s, 'vencidas') for s in abr.get('seguimientos', []) if s.get('est') == 'vencido']
    res = [revisar(i, t, hoy, opp, cot, cuentas) for i, t in items]
    sin = sorted({r['cuenta'] for r in res if not r['regla']})
    fac = facturas_sin_cargar(datos, hoy, opp, cot)
    out = dict(version=VERSION, hoy=hoy_s, lineas=res, sin_regla=sin, facturas_sin_cargar=fac,
               cuentas_cargadas=len(cuentas))
    json.dump(out, open(os.path.join(datos, 'memoria.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n = lambda c: sum(1 for r in res if c in r['codigos'])
    print(f'MEMORIA v{VERSION} · cuentas {len(cuentas)} · ajustes {n("AJUSTAR")} · avisos {n("AVISO")} · box {n("BOX")} · sin regla {len(sin)} · facturas sin cargar {len(fac) if fac is not None else "sin R10"}')
    for r in res:
        if r['codigos'] != ['OK']:
            print(f"{'/'.join(dict.fromkeys(r['codigos'])):13} {r['lista']:8} {r['cuenta']} ({r['ref']}): {' · '.join(r['motivos'])}")
            if 'AJUSTAR' in r['codigos']:
                print(f"{'':13} → acción: {r['accion']}  [loki.py decía: {r['accion_loki'][:80]}]")
    if sin:
        print('SIN_REGLA     ' + ' · '.join(sin))
    for x in fac or []:
        print(f"FACTURA_SIN_CARGAR {x['comp']} {x['fecha']} {x['cliente']} ({x['prod']})")
    if not cuentas:
        print('FALLA: no hay carpeta cuentas/ en DATOS (bajar `cuentas` con ArtifactData list, out_dir=DATOS)')
        return 1
    return 0


def autotest():
    hoy = '2026-11-15'
    casos, mal = 0, 0
    def chk(nombre, cond, det=''):
        nonlocal casos, mal
        casos += 1
        if not cond:
            mal += 1
        print(f"{nombre:6} {'BIEN' if cond else 'MAL '}  {det}")
    def armar(top5=None, segs=None, cuentas=None, opp=None, cot=None, r10=None):
        d = tempfile.mkdtemp()
        json.dump(dict(top5=top5 or [], siguen=[]), open(os.path.join(d, 'urgentes.json'), 'w'))
        json.dump(dict(seguimientos=segs or []), open(os.path.join(d, 'abrir.json'), 'w'))
        json.dump(dict(collections=dict(oportunidades=opp or {}, cotizaciones=cot or {})), open(os.path.join(d, 'respaldo.json'), 'w'))
        os.makedirs(os.path.join(d, 'cuentas'))
        for k, v in (cuentas or {}).items():
            json.dump(v, open(os.path.join(d, 'cuentas', k + '.json'), 'w'))
        if r10 is not None:
            with open(os.path.join(d, 'R10.csv'), 'w', encoding='utf-8') as f:
                w = csv.writer(f, delimiter=';')
                w.writerow(['Empresa', 'Fecha Comprobante', 'Documento', 'Comprobante', 'Cliente', 'Vendedor', 'Total', 'Producto'])
                w.writerows(r10)
        return d
    def lin(d):
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            correr(d, hoy)
        return json.load(open(os.path.join(d, 'memoria.json')))
    fs_opp = {'fs': dict(empresa='Fullsat Internet', proximaFecha='2026-11-16', proximaAccion='Renovar cables 16/11')}
    fs_cot = {'c1': dict(numero='Pendiente (cables)', cliente='GRUPO FULL SAT S.R.L.', oportunidadId='fs')}
    fs_cta = {'fs': dict(empresa='Full Sat', descarta=['ONU por ahora (remanente)'], empuja=['ADSS 48F y 12F'], lleva='ventas')}
    t_fs = dict(cuenta='GRUPO FULL SAT S.R.L.', ref='Pendiente (cables)', accion='preguntar si la traba es precio o plazo', ojo=['el paquete V13 de GPT la marca NO TOCAR'])
    m = lin(armar([t_fs], cuentas=fs_cta, opp=fs_opp, cot=fs_cot))['lineas'][0]
    chk('m1', 'AJUSTAR' in m['codigos'] and '16/11' in ' '.join(m['motivos']), 'próxima fecha futura → AJUSTAR (Full Sat)')
    chk('m2', any('no tocar' in x.lower() for x in m['motivos']), 'marca NO TOCAR de otra fuente → AVISO')
    dyr_cta = {'dyr': dict(empresa='D y R Sistemas', descarta=['ONU FiberHome'], empuja=['OLT y placas'], lleva='ventas')}
    dyr_opp = {'dyr': dict(empresa='DYR Sistemas', proximaFecha='2026-11-10')}
    t_dyr = dict(cuenta='DYR Sistemas', ref='recompra', accion='ofrecer reemplazo ONU FiberHome HG6145F3')
    m = lin(armar([t_dyr], cuentas=dyr_cta, opp=dyr_opp))['lineas'][0]
    chk('m3', 'AJUSTAR' in m['codigos'] and 'OLT' in m['accion'], 'ofrece ONU descartada → AJUSTAR con lo que se empuja (D y R)')
    m = lin(armar([dict(t_dyr, accion='retomar consulta de OLT')], cuentas=dyr_cta, opp=dyr_opp))['lineas'][0]
    chk('m4', m['codigos'] == ['OK'], 'sano: propone OLT a D y R → OK')
    m = lin(armar(segs=[dict(n='NM10', cliente='Jujuy Digital', est='vencido', vence='29/10')]))
    chk('m5', 'BOX' in m['lineas'][0]['codigos'] and 'perdida' in ' '.join(m['lineas'][0]['motivos']), 'vencida → BOX (nunca pregunta de perdida)')
    chk('m6', 'Jujuy Digital' in m['sin_regla'], 'cuenta sin cuentas/<id> → SIN_REGLA')
    ip_cta = {'ip': dict(empresa='Internet Plus (Iplus)', noInsistir=['seguimientos genéricos (9 sin respuesta)'], lleva='ventas')}
    m = lin(armar([dict(cuenta='Iplus S.A.S', ref='NM43', accion='preguntar si la traba es precio o plazo')], cuentas=ip_cta,
                  cot={'c': dict(numero='NM43', cliente='Iplus S.A.S', oportunidadId='ip')}))['lineas'][0]
    chk('m7', 'AVISO' in m['codigos'], 'seguimiento genérico en cuenta que no responde → AVISO')
    tpp = {'t': dict(empresa='TPP', lleva='OTRO VENDEDOR: no contactar')}
    m = lin(armar([dict(cuenta='Telefonía Pública y Privada (TPP)', ref='x', accion='ofrecer drop')], cuentas=tpp, opp={'t': dict(empresa='Telefonía Pública y Privada (TPP)')}))['lineas'][0]
    chk('m8', 'AJUSTAR' in m['codigos'] and 'no contactar' in m['accion'], 'otro vendedor → AJUSTAR no contactar')
    r10 = [['HORIZON TRADING S.A.', '2026-11-12', 'Factura de Venta Electrónica', 'A-00005-00001720', 'CABLENET', 'Ventas Horizon', '3296215', 'Ont'],
           ['HORIZON TRADING S.A.', '2026-10-20', 'Factura de Venta Electrónica', 'A-00005-00001702', 'FULL SAT', 'Nicolas Mayer', '1000', 'Ont'],
           ['HORIZON TRADING S.A.', '2026-11-11', 'Nota de Crédito de Venta', 'A-00005-00000406', 'FULL SAT', 'Nicolas Mayer', '-1000', 'Ont'],
           ['HORIZON TRADING S.A.', '2026-10-15', 'Factura de Venta Electrónica', 'A-00005-00001695', 'FULL SAT', 'Nicolas Mayer', '1000', 'Ont'],
           ['HORIZON TRADING S.A.', '2026-11-12', 'Factura de Venta Electrónica', 'A-00005-00001721', 'FESACOM', '', '5', 'PCB']]
    cot = {'c': dict(numero='NM52', hz_operacion=dict(factura='A-00005-00001720'))}
    m = lin(armar(cuentas=fs_cta, cot=cot, r10=r10))
    comps = [x['comp'] for x in m['facturas_sin_cargar']]
    chk('m9', comps == ['A-00005-00001695'], f'factura sin cargar detectada; cargada, anulada por NC y de otro vendedor quedan afuera → {comps}')
    d = armar([t_fs], cuentas={}, opp=fs_opp, cot=fs_cot)
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        rc = correr(d, hoy)
    chk('m10', rc == 1, 'sabotaje: sin carpeta cuentas → FALLA (exit 1)')
    print(f"AUTOTEST {'OK' if not mal else 'FALLÓ'}: {casos - mal} de {casos} casos")
    return 0 if not mal else 1


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--autotest':
        sys.exit(autotest())
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(correr(sys.argv[1], sys.argv[2]))
