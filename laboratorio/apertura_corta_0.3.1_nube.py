#!/usr/bin/env python3
"""apertura_corta.py 0.3 · 27/11/2026 · apertura de Loki en un bloque corto (Nicolás 27/11: «más precisa y más rápida»).

Solo lee. Fuente: la base de Loki (Turso horizon-nicom90) con la conexión de loki_sql.py, en UN solo pedido HTTP
(la 0.1 lanzaba un proceso y un pedido por consulta). Funciona en la nube y en la PC (busca loki_sql.py al lado o en
%USERPROFILE%\\.loki). Cuando el corte pase a Supabase cambia solo leer(); armar() queda igual.

Uso: apertura_corta.py AAAA-MM-DD [--fuente auto|supabase|turso] [--loki RUTA/loki_sql.py] · apertura_corta.py --autotest

0.3 (27/11, Nicolás: «el CRM queda como pantalla; acomodá todo para actualizarte»): lee también Supabase
(proyecto dvmdwmytlqubllchkeii, API de administración, consulta read_only, una sola consulta que devuelve un JSON).
--fuente auto (por defecto): Supabase si control.mapa marca comercial como «fuente» (después del corte); si no, Turso,
y la cabecera dice que Supabase todavía es foto. La salida es la misma con las dos fuentes.

Cambios de precisión frente a la 0.1:
  - VENCIDAS (D02 + P13): solo las vivas (enviada / espera_*) y sin «sin fondos» ni «postergada». Las que vencieron pero
    ya tienen revisión agendada a futuro van en una línea aparte (no se repiten todos los días como pendiente).
  - VENCEN EN 7 DÍAS: nuevo, para llegar antes y no después.
  - SEGUIMIENTOS: D07 por la ficha misma (otro_vendedor / no_prospectar) y por cuenta (cue_cuentas.trabajar=0), no
    solo por CUIT (las fichas sin CUIT se escapaban). Ganadas y perdidas fuera (las ganadas van en GANADAS SIN ENTREGAR).
  - PORTADA: marca las cuentas que no se trabajan (D07) si alguna se cuela.
  - CONTROLES: NM únicos, edad de cada fuente, versión del script contra el registro.
"""
import collections, datetime as D, importlib.util, json, os, re, sys, time, urllib.request

VERSION = '0.3.1'
VIVAS = ('enviada', 'espera_aprobacion', 'espera_decision')
ENTREGADA = ('confirmado', 'confirmada', 'entregado', 'entregada')
FUERA_P13 = ('sin fondos', 'postergada', 'sin_fondos')


def corto(s, n=70):
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[:n - 1] + '…'


def dd(f):
    f = str(f or '')[:10]
    return f'{f[8:10]}/{f[5:7]}' if len(f) == 10 else f


def armar(d, hoy):
    h = D.date.fromisoformat(hoy)
    lim = (h - D.timedelta(days=7)).isoformat()
    en7 = (h + D.timedelta(days=7)).isoformat()
    out, ctl = [], []
    fu = d.get('fuentes', {})
    out.append(f'LOKI {dd(hoy)} · ' + (d.get('origen', 'Turso') + ' · ') + ' · '.join(f'{k} {dd(v)}' for k, v in sorted(fu.items())))
    por = d.get('portada', [])
    pf = str((por[0].get('calculado') or '') if por else '')[:10]
    out.append(f"Próximo NM: NM{int(d.get('nm_max') or 0) + 1}" + (f' · portada {dd(pf)}' + ('' if pf == hoy else ' (no es de hoy)') if por else ''))

    # 0.3.1 (regla del PM con opción 1 de Nicolás, 27/11): «NMxx (Cliente)» es parte de la misma venta que NMxx y necesita
    # su madre. FALLA si una base se repite sin sufijo o si hay una hija sin madre.
    madres, hijas = collections.Counter(), collections.defaultdict(list)
    for n in d.get('numeros', []):
        m = re.match(r'^NM(\d+)\s*(\(.*\))?\s*$', str(n or '').strip())
        if m:
            (hijas[int(m.group(1))].append(n) if m.group(2) else madres.update([int(m.group(1))]))
    mal = [f'NM{k} ×{v}' for k, v in madres.items() if v > 1] + [f'{v[0]} sin madre' for k, v in hijas.items() if not madres[k]]
    ctl.append(('NM únicos', 'PASA' if not mal and int(d.get('nm_dup') or 0) == 0 else 'FALLA ' + ' · '.join(mal)))
    for nombre, dias in (('CRM', 1), ('Finnegans', 7), ('recompra', 7)):
        corte = fu.get(nombre)
        if corte:
            edad = (h - D.date.fromisoformat(str(corte)[:10])).days
            ctl.append((nombre, 'PASA' if edad <= dias else f'AVISO {edad} días'))
    if d.get('version_registro') and d.get('version_registro') != VERSION:
        ctl.append(('apertura', f"AVISO registro {d['version_registro']} ≠ {VERSION}"))
    out.append('CONTROLES ' + ' · '.join(f'{a} {b}' for a, b in ctl))

    viv = [x for x in d.get('cotizaciones', []) if x.get('estado') in VIVAS
           and not any(p in str(x.get('resultado') or x.get('notas') or '').lower() for p in FUERA_P13)]
    vencio = [x for x in viv if str(x.get('vence') or '')[:10] and str(x['vence'])[:10] < hoy]
    agendadas = [x for x in vencio if str(x.get('revision') or '')[:10] > hoy]
    venc = [x for x in vencio if x not in agendadas]
    pronto = [x for x in viv if hoy <= str(x.get('vence') or '')[:10] <= en7]
    rev = [x for x in viv if x not in vencio and str(x.get('revision') or '')[:10] and str(x['revision'])[:10] <= hoy]
    if venc:
        out.append(f'VENCIDAS ({len(venc)} · D02: nuevo estado o perdida): ' + ' · '.join(
            f"{x['numero']} {corto(x['cliente'], 18)} {dd(x['vence'])}" for x in venc[:6]))
    if agendadas:
        out.append(f'Vencidas con revisión agendada ({len(agendadas)}): ' + ' · '.join(
            f"{x['numero']} {corto(x['cliente'], 14)} rev {dd(x['revision'])}" for x in agendadas[:6]))
    if pronto:
        out.append(f'VENCEN EN 7 DÍAS ({len(pronto)}): ' + ' · '.join(
            f"{x['numero']} {corto(x['cliente'], 18)} {dd(x['vence'])}" for x in sorted(pronto, key=lambda x: x['vence'])[:6]))
    if rev:
        out.append(f'REVISAR HOY ({len(rev)}): ' + ' · '.join(f"{x['numero']} {corto(x['cliente'], 18)}" for x in rev[:6]))

    gan = []
    for x in d.get('ganadas', []):
        if str(x.get('vendedor') or '').lower() == 'otro':
            continue   # venta de otro vendedor (P21): no es posventa de Nicolás
        if str(x.get('entrega') or '').lower() in ENTREGADA:
            continue
        desp = str(x.get('despacho') or '').lower()
        falta = [n for n, v in (('transporte', x.get('transporte')), ('domicilio', x.get('domicilio'))) if not str(v or '').strip()]
        falta.append('confirmar entrega' if desp.startswith(('despachad', 'confirmad')) else 'despacho')
        gan.append((x, falta))
    if gan:
        out.append(f'GANADAS SIN ENTREGAR ({len(gan)}):')
        for x, falta in gan[:6]:
            out.append(f"  {corto(x['numero'], 12)} {corto(x['cliente'], 22)} · falta {', '.join(falta)}")
        if len(gan) > 6:
            out.append(f'  +{len(gan) - 6} más')

    if por:
        out.append('PORTADA:')
        for x in por[:5]:
            marca = ' ⚠ D07' if x.get('fuera') else ''
            out.append(f"  {x.get('puesto')}. {corto(x.get('empresa'), 22)}{marca} · {corto(x.get('accion'), 78)}")

    seg = [x for x in d.get('seguimientos', []) if not x.get('fuera') and x.get('etapa') not in ('ganado', 'perdido')
           and str(x.get('fecha') or '')[:10] and str(x['fecha'])[:10] <= hoy]
    sem = [x for x in seg if str(x['fecha'])[:10] >= lim]
    viejos = len(seg) - len(sem)
    out.append(f'SEGUIMIENTOS de la semana ({len(sem)})' + (f' · {viejos} atrasados de más de 7 días aparte' if viejos else '') + ':')
    for x in sorted(sem, key=lambda x: (x['fecha'], str(x.get('empresa') or '')))[:6]:
        out.append(f"  {dd(x['fecha'])} {corto(x.get('empresa'), 22)} · {corto(x.get('accion'), 70)}")
    if len(sem) > 6:
        out.append(f'  +{len(sem) - 6} más')
    if d.get('continuidad'):
        out.append('CONTINUIDAD: ' + corto(d['continuidad'], 320))
    return '\n'.join(out), {'vencidas': len(venc), 'agendadas': len(agendadas), 'pronto': len(pronto),
                            'ganadas': len(gan), 'semana': len(sem), 'atrasados': viejos}


CONSULTAS = {
    'fuentes': "SELECT fuente, max(corte) corte FROM cargas WHERE fuente IN ('crm:oportunidades','R10','recompra') GROUP BY fuente",
    'continuidad': "SELECT importante FROM continuidad WHERE id='actual'",
    'seguimientos': "SELECT o.empresa, o.etapa, substr(o.proxima_fecha,1,10) fecha, o.proxima_accion accion, "
                    "(COALESCE(o.otro_vendedor,0)=1 OR COALESCE(o.no_prospectar,0)=1 OR EXISTS (SELECT 1 FROM cue_cuentas c "
                    "WHERE c.crm_id=o.id AND c.trabajar=0)) fuera FROM crm_oportunidad o "
                    "WHERE COALESCE(o.archivada,0)=0 AND o.unificada_en IS NULL AND COALESCE(o.proxima_fecha,'')<>''",
    'cotizaciones': "SELECT numero, cliente, estado, vence, revision, resultado, notas FROM crm_cotizacion "
                    "WHERE COALESCE(archivada,0)=0 AND estado IN ('enviada','espera_aprobacion','espera_decision')",
    'ganadas': "SELECT c.numero, c.cliente, c.despacho, c.entrega, c.pago, o.transporte, (SELECT json_extract(k.data,'$.vendedor') FROM crm k WHERE k.coleccion='cotizaciones' AND k.id=c.id) vendedor, COALESCE(o.domicilio,c.domicilio) domicilio "
               "FROM crm_cotizacion c LEFT JOIN crm_oportunidad o ON o.id=c.oportunidad_id WHERE c.estado='aceptada' "
               "AND COALESCE(c.archivada,0)=0 AND COALESCE(c.fecha_ganada,c.fecha) >= date('now','-60 days') "
               "ORDER BY COALESCE(c.fecha_ganada,c.fecha) DESC, c.numero",
    'portada': "SELECT p.puesto, p.empresa, p.accion, p.calculado, (COALESCE(o.otro_vendedor,0)=1 OR COALESCE(o.no_prospectar,0)=1 "
               "OR EXISTS (SELECT 1 FROM cue_cuentas c WHERE c.crm_id=p.crm_id AND c.trabajar=0)) fuera "
               "FROM por_dia p LEFT JOIN crm_oportunidad o ON o.id=p.crm_id ORDER BY p.puesto LIMIT 10",
    'nm_dup': "SELECT count(*) n FROM (SELECT numero FROM crm_cotizacion WHERE numero GLOB 'NM[0-9]*' GROUP BY numero HAVING count(*)>1)",
    'nm_max': "SELECT max(CAST(substr(numero,3) AS INTEGER)) m FROM crm_cotizacion WHERE numero GLOB 'NM[0-9]*'",
    'version': "SELECT version FROM scripts WHERE nombre='apertura_corta.py'",
    'numeros': "SELECT numero FROM crm_cotizacion WHERE COALESCE(archivada,0)=0 AND numero LIKE 'NM%'",
}


def cargar_loki(ruta):
    for r in [ruta, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'loki_sql.py'),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'BIN', 'loki_sql.py'),
              os.path.expandvars(r'%USERPROFILE%\.loki\loki_sql.py')]:
        if r and os.path.isfile(r):
            spec = importlib.util.spec_from_file_location('loki_sql', r)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise SystemExit('FALLA: no encuentro loki_sql.py (pasá --loki RUTA)')


def leer(loki):
    db = loki.conectar()
    try:
        res = db.run([(s, []) for s in CONSULTAS.values()])
    finally:
        db.close()
    t = {k: [dict(zip(c, f)) for f in filas] for k, (c, filas) in zip(CONSULTAS, res)}
    nombres = {'crm:oportunidades': 'CRM', 'R10': 'Finnegans', 'recompra': 'recompra'}
    return {
        'fuentes': {nombres[x['fuente']]: x['corte'] for x in t['fuentes']},
        'continuidad': t['continuidad'][0]['importante'] if t['continuidad'] else '',
        'seguimientos': t['seguimientos'], 'cotizaciones': t['cotizaciones'], 'ganadas': t['ganadas'],
        'portada': t['portada'], 'nm_dup': t['nm_dup'][0]['n'], 'nm_max': t['nm_max'][0]['m'],
        'version_registro': (t['version'][0]['version'] if t['version'] else None),
        'numeros': [x['numero'] for x in t['numeros']],
    }


SUPA = 'https://api.supabase.com/v1/projects/dvmdwmytlqubllchkeii/database/query'
SQL_SUPA = """SELECT json_build_object(
 'mapa', (SELECT json_object_agg(tabla, estado) FROM control.mapa),
 'fuentes', json_build_object(
    'CRM', (SELECT max(mudado)::date FROM comercial.oportunidad),
    'Finnegans', (SELECT max(cuando)::date FROM control.mudanza WHERE modulo='finnegans' AND resultado='PASA'),
    'recompra', (SELECT max(mudado)::date FROM motores.recompra_cliente)),
 'continuidad', (SELECT importante FROM operacion.continuidad WHERE id='actual'),
 'seguimientos', (SELECT json_agg(x) FROM (SELECT o.empresa, o.etapa, substr(o.proxima_fecha,1,10) fecha, o.proxima_accion accion,
    (coalesce(o.otro_vendedor::int,0)=1 OR coalesce(o.no_prospectar::int,0)=1 OR EXISTS (SELECT 1 FROM clientes.cuenta c
     WHERE c.crm_id=o.id AND c.trabajar::int=0))::int fuera FROM comercial.oportunidad o
    WHERE coalesce(o.archivada::int,0)=0 AND o.unificada_en IS NULL AND coalesce(o.proxima_fecha,'')<>'') x),
 'cotizaciones', (SELECT json_agg(x) FROM (SELECT numero, cliente, estado, vence, revision, resultado, notas FROM comercial.cotizacion
    WHERE coalesce(archivada::int,0)=0 AND estado IN ('enviada','espera_aprobacion','espera_decision')) x),
 'ganadas', (SELECT json_agg(x) FROM (SELECT c.numero, c.cliente, c.despacho, c.entrega, c.pago, c.vendedor, o.transporte,
    coalesce(o.domicilio,c.domicilio) domicilio FROM comercial.cotizacion c LEFT JOIN comercial.oportunidad o ON o.id=c.oportunidad_id
    WHERE c.estado='aceptada' AND coalesce(c.archivada::int,0)=0
    AND substr(coalesce(c.fecha_ganada,c.fecha),1,10) >= (now() - interval '60 days')::date::text
    ORDER BY coalesce(c.fecha_ganada,c.fecha) DESC, c.numero COLLATE "C") x),
 'portada', (SELECT json_agg(x ORDER BY x.puesto) FROM (SELECT p.puesto, p.empresa, p.accion, p.calculado,
    (coalesce(o.otro_vendedor::int,0)=1 OR coalesce(o.no_prospectar::int,0)=1 OR EXISTS (SELECT 1 FROM clientes.cuenta c
     WHERE c.crm_id=p.crm_id AND c.trabajar::int=0))::int fuera
    FROM motores.portada p LEFT JOIN comercial.oportunidad o ON o.id=p.crm_id ORDER BY p.puesto LIMIT 10) x),
 'numeros', (SELECT json_agg(numero) FROM comercial.cotizacion WHERE coalesce(archivada::int,0)=0 AND numero LIKE 'NM%'),
 'nm_max', (SELECT max(substring(numero from '^NM([0-9]+)')::int) FROM comercial.cotizacion)
) j"""


def leer_supabase():
    body = json.dumps({'query': SQL_SUPA, 'read_only': True}).encode()
    rq = urllib.request.Request(SUPA, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(rq, timeout=60) as r:
        j = json.load(r)[0]['j']
    for k in ('seguimientos', 'cotizaciones', 'ganadas', 'portada', 'numeros'):
        j[k] = j.get(k) or []
    j['fuentes'] = {k: v for k, v in (j.get('fuentes') or {}).items() if v}
    j['nm_dup'] = 0      # lo cubre el control por base de número (numeros)
    return j


def corte_hecho(mapa):
    """Supabase es la fuente de lo comercial cuando el mapa lo marca así (después del corte, con hacelo)."""
    return all(str((mapa or {}).get(t, '')).lower() == 'fuente' for t in ('oportunidad', 'cotizacion'))


def autotest():
    hoy = '2026-11-27'
    d = {
        'fuentes': {'CRM': '2026-11-27', 'Finnegans': '2026-11-15', 'recompra': '2026-11-26'},
        'continuidad': 'prueba',
        'seguimientos': [
            {'empresa': 'Hoy SA', 'etapa': 'cotizado', 'fecha': '2026-11-27', 'accion': 'llamar', 'fuera': 0},
            {'empresa': 'Ajena SA', 'etapa': 'contactado', 'fecha': '2026-11-26', 'accion': 'no va (D07)', 'fuera': 1},
            {'empresa': 'Ganada SA', 'etapa': 'ganado', 'fecha': '2026-11-26', 'accion': 'posventa', 'fuera': 0},
            {'empresa': 'Vieja SA', 'etapa': 'contactado', 'fecha': '2026-10-01', 'accion': 'atrasada', 'fuera': 0},
            {'empresa': 'Futura SA', 'etapa': 'contactado', 'fecha': '2026-12-04', 'accion': 'todavía no', 'fuera': 0},
        ],
        'cotizaciones': [
            {'numero': 'NM10', 'cliente': 'Vencida', 'estado': 'enviada', 'vence': '2026-11-20', 'revision': ''},
            {'numero': 'NM13', 'cliente': 'Agendada', 'estado': 'enviada', 'vence': '2026-10-17', 'revision': '2027-04-17'},
            {'numero': 'NM14', 'cliente': 'SinFondos', 'estado': 'enviada', 'vence': '2026-10-17', 'revision': '', 'resultado': 'sin fondos'},
            {'numero': 'NM11', 'cliente': 'Revisar', 'estado': 'enviada', 'vence': '2026-12-20', 'revision': '2026-11-27'},
            {'numero': 'NM12', 'cliente': 'Pronto', 'estado': 'enviada', 'vence': '2026-12-02', 'revision': '2026-12-05'},
        ],
        'ganadas': [
            {'numero': 'NM52', 'cliente': 'Despachada', 'despacho': 'despachado 24/11', 'entrega': 'pendiente', 'pago': 'confirmado', 'transporte': 'x', 'domicilio': 'y'},
            {'numero': 'NM59', 'cliente': 'Sin despacho', 'despacho': 'pendiente', 'entrega': 'pendiente', 'pago': 'pendiente', 'transporte': '', 'domicilio': 'y'},
            {'numero': 'S/N FA 1699', 'cliente': 'Ajeno', 'despacho': '', 'entrega': '', 'pago': '', 'transporte': '', 'domicilio': '', 'vendedor': 'otro'},
            {'numero': 'NM40', 'cliente': 'Entregada', 'despacho': 'despachado', 'entrega': 'confirmado', 'pago': 'confirmado', 'transporte': 'x', 'domicilio': 'y'},
        ],
        'portada': [{'puesto': 1, 'empresa': 'P', 'accion': 'a', 'calculado': '2026-11-26', 'fuera': 1}],
        'nm_dup': 0, 'nm_max': 62, 'version_registro': '0.1', 'numeros': ['NM37', 'NM37 (Infinitel)', 'NM40'],
    }
    txt, n = armar(d, hoy)
    casos = [
        ('vencida D02', n['vencidas'] == 1 and 'NM10' in txt),
        ('vencida con revisión agendada aparte', n['agendadas'] == 1 and 'NM13 Agendada rev 17/04' in txt),
        ('P13 sin fondos fuera', 'NM14' not in txt),
        ('vencen en 7 días', n['pronto'] == 1 and 'NM12 Pronto 02/12' in txt),
        ('revisar hoy', 'REVISAR HOY (1): NM11' in txt),
        ('ganadas: entregada fuera', n['ganadas'] == 2 and 'NM40' not in txt),
        ('despachada pide confirmar entrega', 'NM52 Despachada · falta confirmar entrega' in txt),
        ('sin despacho (pago es de otra área, D08)', 'NM59 Sin despacho · falta transporte, despacho' in txt and 'pago' not in txt),
        ('venta de otro vendedor fuera', 'Ajeno' not in txt),
        ('NMxx (Cliente) con su madre no es duplicado', 'NM únicos PASA' in txt),
        ('NM repetido sin sufijo FALLA', 'FALLA NM40 ×2' in armar(dict(d, numeros=['NM40', 'NM40']), hoy)[0]),
        ('hija sin madre FALLA', 'NM90 (X) sin madre' in armar(dict(d, numeros=['NM90 (X)']), hoy)[0]),
        ('D07 fuera de seguimientos', 'Ajena SA' not in txt),
        ('ganadas fuera de seguimientos', 'Ganada SA' not in txt),
        ('semana vs atrasados', n['semana'] == 1 and n['atrasados'] == 1),
        ('futuros fuera', 'Futura SA' not in txt),
        ('portada vieja avisada', '(no es de hoy)' in txt),
        ('portada D07 marcada', '⚠ D07' in txt),
        ('próximo NM', 'Próximo NM: NM63' in txt),
        ('edad Finnegans', 'Finnegans AVISO 12 días' in txt),
        ('versión contra registro', f'registro 0.1 ≠ {VERSION}' in txt),
        ('corta', len(txt) < 2000),
        ('corte: comercial fuente', corte_hecho({'oportunidad': 'fuente', 'cotizacion': 'fuente'})),
        ('antes del corte: Turso', not corte_hecho({'oportunidad': 'controles', 'cotizacion': 'fuente'})),
    ]
    ok = sum(1 for _, b in casos if b)
    for nombre, b in casos:
        if not b:
            print('FALLA ·', nombre)
    print(f'autotest apertura_corta {VERSION}: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    if not a:
        sys.exit(__doc__)
    hoy = a[0]
    D.date.fromisoformat(hoy)
    t0 = time.time()
    fuente = a[a.index('--fuente') + 1] if '--fuente' in a else 'auto'
    d = None
    if fuente in ('auto', 'supabase'):
        try:
            sp = leer_supabase()
            if fuente == 'supabase' or corte_hecho(sp.get('mapa')):
                d, d['origen'] = sp, 'Supabase'
            else:
                foto = (sp.get('fuentes') or {}).get('CRM')
                aviso = f'Turso (Supabase es foto del {dd(foto)} hasta el corte)'
        except Exception as e:  # noqa: BLE001
            if fuente == 'supabase':
                raise SystemExit(f'FALLA Supabase: {e}')
            aviso = f'Turso (Supabase no respondió: {str(e)[:60]})'
    if d is None:
        d = leer(cargar_loki(a[a.index('--loki') + 1] if '--loki' in a else None))
        d['origen'] = aviso if fuente == 'auto' else 'Turso'
    texto, _ = armar(d, hoy)
    print(texto)
    print(f'({len(texto)} caracteres · {time.time() - t0:.1f} s · apertura_corta {VERSION})')
