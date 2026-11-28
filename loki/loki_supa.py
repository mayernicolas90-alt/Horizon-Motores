#!/usr/bin/env python3
"""loki_supa.py 0.1 · 28/11/2026 · Loki opera leyendo Supabase (Nicolás 28/11: «empezá a operar de Supabase»).

Solo lee (cada consulta va con read_only). Proyecto dvmdwmytlqubllchkeii, API de administración: en la nube el token lo pone
el proxy del entorno; en la PC sale del Administrador de credenciales («Loki/Supabase-horizon»), igual que espejo.py.

Uso (python3 -I):
  loki_supa.py apertura            la apertura del día desde la vista apertura.hoy (la arma el PM; reglas de apertura_corta 0.2)
  loki_supa.py fuentes             fecha de cada fuente y estado del mapa de la mudanza
  loki_supa.py cliente CUIT|texto  todo lo de una cuenta: oportunidad, cotizaciones, muestras, recompra, puntaje (regla 1: todo cuelga del CUIT)
  loki_supa.py sql "SELECT …"      consulta libre de solo lectura
  loki_supa.py --autotest
"""
import json, re, sys
import importlib.util, os

AQUI = os.path.dirname(os.path.abspath(__file__))
VERSION = '0.1'


def _espejo():
    sp = importlib.util.spec_from_file_location('espejo', os.path.join(AQUI, 'espejo.py'))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def leer(sql):
    if not re.match(r'(?is)^\s*(select|with)\b', sql):
        raise SystemExit('loki_supa solo lee: la consulta tiene que empezar con SELECT o WITH')
    return _espejo().supa(sql, solo_lectura=True)


def dd(f):
    f = str(f or '')[:10]
    return f'{f[8:10]}/{f[5:7]}' if len(f) == 10 else f


def armar_apertura(a):
    out = [f"LOKI · Supabase · datos al {dd(a.get('hoy'))} · Próximo NM: {a.get('proximo_nm')}"]
    out.append('CONTROLES ' + ' · '.join(a.get('controles') or []))
    for k, t in (('vencidas', 'VENCIDAS'), ('vencidas_con_revision', 'Vencidas con revisión agendada'),
                 ('vencen_7d', 'VENCEN EN 7 DÍAS'), ('revisar', 'REVISAR HOY')):
        if a.get(k):
            out.append(f'{t} ({len(a[k])}): ' + ' · '.join(a[k][:8]))
    g = a.get('ganadas_sin_entregar') or {}
    if g.get('n'):
        out.append(f"GANADAS SIN ENTREGAR ({g['n']}):")
        out += ['  ' + x for x in g.get('top', [])]
    p = a.get('portada') or {}
    if p.get('top'):
        out.append('PORTADA' + (' (no es de hoy)' if p.get('vieja') else '') + ': ' + ' · '.join(p['top']))
    s = a.get('seguimientos') or {}
    if s:
        out.append(f"SEGUIMIENTOS de la semana ({s.get('semana', 0)}) · {s.get('atrasados', 0)} atrasados aparte: " + ' · '.join(s.get('top', [])))
    c = a.get('continuidad') or {}
    if c:
        out.append(f"CONTINUIDAD {dd(c.get('fecha'))} · bitácora abierta {c.get('bitacora_abierta')}")
    return '\n'.join(out)


def apertura():
    r = leer('SELECT apertura FROM apertura.hoy')
    print(armar_apertura(r[0]['apertura']) if r else 'FALLA: apertura.hoy vacía')


def fuentes():
    for x in leer("SELECT tabla, estado, dueno, actualizado::date FROM control.mapa ORDER BY esquema, tabla"):
        print(f"  {x['tabla']:18} {x['estado']:12} dueño {x['dueno']:5} {x['actualizado']}")
    for x in leer('SELECT * FROM apertura.fuentes'):
        print('  ' + ' · '.join(f'{k} {v}' for k, v in x.items()))


def cliente(c):
    d = re.sub(r'\D', '', c)
    filtro = f"cuit11='{d}'" if len(d) == 11 else f"empresa ILIKE {_espejo().lit('%' + c + '%')}"
    ops = leer(f'SELECT id, empresa, cuit, etapa, monto, proxima_fecha, proxima_accion FROM comercial.oportunidad WHERE {filtro} LIMIT 5')
    print(f'OPORTUNIDADES ({len(ops)})')
    for o in ops:
        print(f"  {o['empresa']} · {o['cuit'] or 'sin CUIT'} · {o['etapa']} · USD {o['monto'] or 0} · próxima {dd(o['proxima_fecha'])} {o['proxima_accion'] or ''}"[:200])
    ids = ', '.join("'" + o['id'] + "'" for o in ops) or "''"
    for x in leer(f'SELECT numero, estado, fecha, vence, total, despacho, entrega FROM comercial.cotizacion WHERE oportunidad_id IN ({ids}) ORDER BY fecha DESC LIMIT 10'):
        print(f"  COT {x['numero']} · {x['estado']} · {dd(x['fecha'])} · vence {dd(x['vence'])} · USD {x['total']} · despacho {x['despacho'] or '—'} · entrega {x['entrega'] or '—'}"[:200])
    cuits = {o['cuit'] for o in ops if o['cuit']}
    if cuits:
        cs = ', '.join("'" + x + "'" for x in cuits)
        for x in leer(f'SELECT cliente, estado, foco_sku, ultima, proxima FROM motores.recompra_cliente WHERE cuit IN ({cs})'):
            print(f"  RECOMPRA {x['estado']} · foco {x['foco_sku']} · última {dd(x['ultima'])} · próxima {dd(x['proxima'])}")


def autotest():
    a = {'hoy': '2026-11-28', 'proximo_nm': 'NM63', 'controles': ['NM únicos: PASA'], 'vencidas': None,
         'vencen_7d': ['NM54 Net Acebal 01/12'], 'ganadas_sin_entregar': {'n': 1, 'top': ['NM52 Cablenet: falta confirmar entrega']},
         'portada': {'vieja': True, 'top': ['1. San Luis CTV']}, 'seguimientos': {'semana': 2, 'atrasados': 5, 'top': ['20/11 X']},
         'continuidad': {'fecha': '2026-11-27', 'bitacora_abierta': 13}}
    t = armar_apertura(a)
    casos = [('cabecera con fecha y NM', 'datos al 28/11 · Próximo NM: NM63' in t), ('vacío no se muestra', 'VENCIDAS' not in t),
             ('vencen 7 días', 'VENCEN EN 7 DÍAS (1)' in t), ('portada vieja avisada', '(no es de hoy)' in t),
             ('ganadas', 'GANADAS SIN ENTREGAR (1)' in t)]
    try:
        leer('DELETE FROM x')
        casos.append(('rechaza escritura', False))
    except SystemExit:
        casos.append(('rechaza escritura', True))
    ok = sum(b for _, b in casos)
    for n, b in casos:
        print(('  OK    ' if b else '  FALLA ') + n)
    print(f'autotest loki_supa: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    if a[:1] == ['apertura']:
        apertura()
    elif a[:1] == ['fuentes']:
        fuentes()
    elif a[:1] == ['cliente'] and len(a) > 1:
        cliente(' '.join(a[1:]))
    elif a[:1] == ['sql'] and len(a) > 1:
        for r in leer(a[1]):
            print(json.dumps(r, ensure_ascii=False, default=str))
    else:
        print(__doc__)
