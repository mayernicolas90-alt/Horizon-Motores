#!/usr/bin/env python3
"""apertura_corta.py 0.2 · 27/11/2026 · apertura de Loki en un bloque corto (Nicolás 27/11: «mejorar precisión y arranque»).

No escribe en el CRM ni en la base (salvo lo que ya hace `abrir`). Fuente hoy: la base de Loki (Turso horizon-nicom90) por loki_sql.py sql.
Cuando el PM arme apertura.hoy en Supabase, cambia la fuente (leer_*) y no la salida (armar).

Uso (python -I -X utf8):
  apertura_corta.py AAAA-MM-DD --crm CARPETA [--incremental] [--origen ID]
                                   arranque en un paso: corre `loki_sql.py abrir` con el CRM, muestra solo sus
                                   controles (si hay FALLA, para) y arma la apertura
  apertura_corta.py AAAA-MM-DD     solo la apertura (si `abrir` ya corrió)
  apertura_corta.py --autotest     casos sin datos reales

0.2 (27/11, «hacelo» de Nicolás):
  - GANADAS SIN ENTREGAR: la cabecera y la lista coinciden (decía 9 y mostraba 8); más de 12 → «+N más».
  - Control vence≥fecha: FALLA si una cotización vence antes de su propia fecha (caso NM48).
  - VENCIDAS (D02 + bitácora #267): nada pasa a perdida sin que Nicolás lo diga; por defecto se pasan 5 días.
    Lista todas y deja el cambio armado en C:\\Loki\\propuestas\\prorroga_AAAA-MM-DD.json para escribir con el «hacelo».
  - --crm: abrir + apertura en un solo comando.

Precisión frente a la apertura de loki_sql 1.18:
  - VENCIDAS (D02): cotización viva (enviada / espera_*) con vence < hoy. Antes salía «ninguna».
  - GANADAS SIN ENTREGAR: mira despacho y entrega, no solo transporte/domicilio (caso NM52).
  - SEGUIMIENTOS: los de la semana aparte de los atrasados de más de 7 días.
  - Cuentas de D07 (otro vendedor / no prospectar) fuera de seguimientos.
  - Portada con su fecha de cálculo: si no es de hoy, lo dice.
"""
import datetime as D, json, os, re, subprocess, sys

VIVAS = ('enviada', 'espera_aprobacion', 'espera_decision')
ENTREGADA = ('confirmado', 'confirmada', 'entregado', 'entregada')
DIAS_PRORROGA = 5        # Nicolás 27/11 (bitácora #267)
MAX_GAN = 12
RAIZ = os.environ.get('LOKI_RAIZ', r'C:\Loki')
ORIGEN_CRM = '5SPm4UZTgiF5JXx7GKTybq'
CLAVES_ABRIR = ('ARRANQUE', 'CONTROL', 'CADENA', 'FALLA', 'AVISO')


def corto(s, n=70):
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[:n - 1] + '…'


def cuit11(c):
    return ''.join(ch for ch in str(c or '') if ch.isdigit())


# ------------------------------------------------------------------ armado (puro, se prueba en el autotest)
def armar(d, hoy):
    """d: dict con fuentes, continuidad, excluidos, seguimientos, cotizaciones, ganadas, portada, nm_dup, nm_max."""
    lim = (D.date.fromisoformat(hoy) - D.timedelta(days=7)).isoformat()
    out, ctl = [], []
    fu = d.get('fuentes', {})
    out.append(f'APERTURA {hoy} · fuentes: ' + ' · '.join(f'{k} {str(v)[:10]}' for k, v in sorted(fu.items())))
    por = d.get('portada', [])
    pf = str((por[0].get('calculado') or '') if por else '')[:10]
    out.append(f"Próximo NM: NM{int(d.get('nm_max') or 0) + 1}" + (f' · portada calculada {pf}' + ('' if pf == hoy else ' (NO ES DE HOY)') if por else ''))
    ctl.append(('NM únicos', 'PASA' if int(d.get('nm_dup') or 0) == 0 else f"FALLA ({d['nm_dup']})"))
    for nombre, dias in (('CRM', 1), ('Finnegans', 7), ('recompra', 7)):
        corte = fu.get(nombre)
        if corte:
            edad = (D.date.fromisoformat(hoy) - D.date.fromisoformat(str(corte)[:10])).days
            ctl.append((f'edad {nombre}', 'PASA' if edad <= dias else f'AVISO ({str(corte)[:10]})'))
    viv = [x for x in d.get('cotizaciones', []) if x.get('estado') in VIVAS]
    # 0.2 control: una cotización no puede vencer antes de su propia fecha (27/11: NM48 fecha 03/11, vence 26/09)
    malas = [x for x in viv if str(x.get('fecha') or '')[:10] and str(x.get('vence') or '')[:10]
             and str(x['vence'])[:10] < str(x['fecha'])[:10]]
    ctl.append(('vence≥fecha', 'PASA' if not malas else 'FALLA (' + ', '.join(
        f"{x['numero']} fecha {str(x['fecha'])[:10]} vence {str(x['vence'])[:10]}" for x in malas) + ')'))
    out.append('CONTROLES ' + ' · '.join(f'{a} {b}' for a, b in ctl))

    venc = [x for x in viv if str(x.get('vence') or '')[:10] and str(x['vence'])[:10] < hoy]
    rev = [x for x in viv if x not in venc and str(x.get('revision') or x.get('vence') or '')[:10]
           and str(x.get('revision') or x.get('vence'))[:10] <= hoy]
    nuevo = prorroga(hoy)
    if venc:   # 0.2 D02 + bitácora #267: nada pasa a perdida sin que Nicolás lo diga; por defecto se pasa 5 días
        out.append(f'VENCIDAS ({len(venc)}, D02: se pasan {DIAS_PRORROGA} días → {nuevo} salvo que digas perdida): ' + ' · '.join(
            f"{x['numero']} {corto(x['cliente'], 22)} venció {str(x['vence'])[:10]}" for x in venc))
    if rev:
        out.append(f'REVISAR HOY ({len(rev)}): ' + ' · '.join(f"{x['numero']} {corto(x['cliente'], 22)}" for x in rev[:8]))

    gan = []
    for x in d.get('ganadas', []):
        desp = str(x.get('despacho') or '').lower()
        if str(x.get('entrega') or '').lower() in ENTREGADA:
            continue
        falta = [n for n, v in (('transporte', x.get('transporte')), ('domicilio', x.get('domicilio'))) if not str(v or '').strip()]
        falta.append('entrega' if desp.startswith('despachad') else 'despacho')
        gan.append((x, falta))
    if gan:   # 0.2: el número de la cabecera y las líneas siempre coinciden (27/11 decía 9 y mostraba 8)
        out.append(f'GANADAS SIN ENTREGAR ({len(gan)}):')
        for x, falta in gan[:MAX_GAN]:
            out.append(f"  {x['numero']} {corto(x['cliente'], 26)} · falta {', '.join(falta)}")
        if len(gan) > MAX_GAN:
            out.append(f'  +{len(gan) - MAX_GAN} más')

    if por:
        out.append('PORTADA (top 5):')
        for x in por[:5]:
            out.append(f"  {x.get('puesto')}. {corto(x.get('empresa'), 24)} · {corto(x.get('accion'), 80)}")

    excl = set(d.get('excluidos', []))
    seg = [x for x in d.get('seguimientos', []) if cuit11(x.get('cuit')) not in excl or not cuit11(x.get('cuit'))]
    seg = [x for x in seg if str(x.get('fecha') or '')[:10] and str(x['fecha'])[:10] <= hoy]
    sem = [x for x in seg if str(x['fecha'])[:10] >= lim]
    viejos = len(seg) - len(sem)
    out.append(f'SEGUIMIENTOS de la semana ({len(sem)})' + (f' · además {viejos} atrasados de más de 7 días' if viejos else '') + ':')
    for x in sorted(sem, key=lambda x: x['fecha'])[:8]:
        out.append(f"  {str(x['fecha'])[:10]} {corto(x.get('empresa'), 24)} · {corto(x.get('accion'), 70)}")
    if len(sem) > 8:
        out.append(f'  +{len(sem) - 8} más')
    if d.get('continuidad'):
        out.append('CONTINUIDAD: ' + corto(d['continuidad'], 600))
    propuesta = [{'doc_id': x.get('id'), 'numero': x['numero'], 'cliente': x.get('cliente'),
                  'vence_actual': str(x['vence'])[:10], 'vence_nuevo': nuevo} for x in venc]
    return '\n'.join(out), {'vencidas': len(venc), 'ganadas': len(gan), 'semana': len(sem), 'atrasados': viejos,
                            'malas': len(malas), 'prorroga': propuesta}


def prorroga(hoy):
    return (D.date.fromisoformat(hoy) + D.timedelta(days=DIAS_PRORROGA)).isoformat()


def guardar_prorroga(propuesta, hoy):
    """Deja armado el cambio de vencimientos para escribirlo en el CRM con el «hacelo» (no escribe nada en el CRM)."""
    if not propuesta:
        return None
    car = os.path.join(RAIZ, 'propuestas')
    os.makedirs(car, exist_ok=True)
    ruta = os.path.join(car, f'prorroga_{hoy}.json')
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({'hoy': hoy, 'coleccion': 'cotizaciones', 'cambio': 'vence', 'items': propuesta}, f, ensure_ascii=False, indent=1)
    return ruta


# ------------------------------------------------------------------ lectura (Turso por loki_sql.py)
def q(sql):
    loki = os.path.expandvars(r'%USERPROFILE%\.loki')
    r = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(loki, 'conauth.py'), os.path.join(loki, 'loki_sql.py'), 'sql', sql],
                       capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        raise SystemExit('FALLA consulta: ' + ((r.stderr.strip().splitlines() or ['?'])[-1])[:200])
    return [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]


def leer_turso():
    nombres = {'crm:oportunidades': 'CRM', 'R10': 'Finnegans', 'R8': 'stock R8', 'recompra': 'recompra'}
    fu = {nombres[x['fuente']]: x['corte'] for x in q(
        "SELECT fuente, max(corte) corte FROM cargas WHERE fuente IN ('crm:oportunidades','R10','R8','recompra') GROUP BY fuente")}
    cont = q("SELECT importante FROM continuidad ORDER BY actualizado DESC, rowid DESC LIMIT 1")
    return {
        'fuentes': fu,
        'continuidad': cont[0]['importante'] if cont else '',
        'excluidos': [x['c'] for x in q("SELECT replace(cuit,'-','') c FROM crm_oportunidad WHERE (otro_vendedor=1 OR no_prospectar=1) AND COALESCE(cuit,'')<>''")],
        'seguimientos': q("SELECT empresa, cuit, substr(proxima_fecha,1,10) fecha, proxima_accion accion FROM crm_oportunidad "
                          "WHERE COALESCE(archivada,0)=0 AND unificada_en IS NULL AND COALESCE(proxima_fecha,'')<>''"),
        'cotizaciones': q("SELECT id, numero, cliente, estado, fecha, vence, revision FROM crm_cotizacion WHERE COALESCE(archivada,0)=0 "
                          "AND estado IN ('enviada','espera_aprobacion','espera_decision')"),
        'ganadas': q("SELECT c.numero, c.cliente, c.despacho, c.entrega, o.transporte, COALESCE(o.domicilio,c.domicilio) domicilio "
                     "FROM crm_cotizacion c LEFT JOIN crm_oportunidad o ON o.id=c.oportunidad_id WHERE c.estado='aceptada' "
                     "AND COALESCE(c.archivada,0)=0 AND COALESCE(c.fecha_ganada,c.fecha) >= date('now','-60 days') "
                     "ORDER BY COALESCE(c.fecha_ganada,c.fecha) DESC"),
        'portada': q("SELECT puesto, empresa, accion, calculado FROM por_dia ORDER BY puesto LIMIT 10"),
        'nm_dup': q("SELECT count(*) n FROM (SELECT numero FROM crm_cotizacion WHERE numero GLOB 'NM[0-9]*' GROUP BY numero HAVING count(*)>1)")[0]['n'],
        'nm_max': q("SELECT max(CAST(substr(numero,3) AS INTEGER)) m FROM crm_cotizacion WHERE numero GLOB 'NM[0-9]*'")[0]['m'],
    }


def filtrar_abrir(salida):
    """De la salida de `loki_sql.py abrir` quedan solo los controles. Devuelve (líneas, hay_falla)."""
    lin = [l.rstrip() for l in salida.splitlines() if any(k in l for k in CLAVES_ABRIR)]
    return lin, any(re.search(r'\bFALLA\b', l) for l in lin)


def abrir(hoy, crm, origen, incremental):
    """Corre `loki_sql.py abrir` con el CRM. Imprime solo los controles; devuelve True si hubo FALLA (no seguir)."""
    loki = os.path.expandvars(r'%USERPROFILE%\.loki')
    cmd = [sys.executable, '-I', '-X', 'utf8', os.path.join(loki, 'conauth.py'), os.path.join(loki, 'loki_sql.py'),
           'abrir', RAIZ, hoy, '--crm', crm, '--origen', origen] + (['--incremental'] if incremental else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    lin, falla = filtrar_abrir((r.stdout or '') + '\n' + (r.stderr or ''))
    if r.returncode != 0:
        falla = True
        ult = ((r.stderr or r.stdout or '').strip().splitlines() or ['?'])[-1]
        lin.append(f'FALLA abrir terminó con código {r.returncode}: ' + corto(ult, 200))
    for l in lin:
        print(l)
    if falla:
        print('NO SIGUE: hay FALLA en abrir; la apertura no se arma hasta resolverla.')
    return falla


# ------------------------------------------------------------------ autotest (sin datos reales)
def autotest():
    hoy = '2026-11-27'
    d = {
        'fuentes': {'CRM': '2026-11-27', 'Finnegans': '2026-11-15', 'recompra': '2026-11-26'},
        'continuidad': 'prueba',
        'excluidos': ['30123456789'],
        'seguimientos': [
            {'empresa': 'Hoy SA', 'cuit': '30-11111111-1', 'fecha': '2026-11-27', 'accion': 'llamar'},
            {'empresa': 'Ajena SA', 'cuit': '30-12345678-9', 'fecha': '2026-11-26', 'accion': 'no va (D07)'},
            {'empresa': 'Vieja SA', 'cuit': '', 'fecha': '2026-10-01', 'accion': 'atrasada'},
            {'empresa': 'Futura SA', 'cuit': '', 'fecha': '2026-12-04', 'accion': 'todavía no'},
        ],
        'cotizaciones': [
            {'id': 'd10', 'numero': 'NM10', 'cliente': 'Vencida', 'estado': 'enviada', 'fecha': '2026-11-05', 'vence': '2026-11-20', 'revision': ''},
            {'numero': 'NM11', 'cliente': 'Revisar', 'estado': 'enviada', 'fecha': '2026-11-20', 'vence': '2026-12-10', 'revision': '2026-11-27'},
            {'numero': 'NM12', 'cliente': 'Al día', 'estado': 'enviada', 'fecha': '2026-11-20', 'vence': '2026-12-10', 'revision': '2026-12-05'},
        ],
        'ganadas': [
            {'numero': 'NM52', 'cliente': 'Despachada', 'despacho': 'despachado 24/11', 'entrega': 'pendiente', 'transporte': 'x', 'domicilio': 'y'},
            {'numero': 'NM59', 'cliente': 'Sin despacho', 'despacho': 'pendiente', 'entrega': 'pendiente', 'transporte': '', 'domicilio': 'y'},
            {'numero': 'NM40', 'cliente': 'Entregada', 'despacho': 'despachado', 'entrega': 'confirmado', 'transporte': 'x', 'domicilio': 'y'},
        ] + [{'numero': f'NM7{i}', 'cliente': f'Muchas {i}', 'despacho': '', 'entrega': '', 'transporte': 'x', 'domicilio': 'y'} for i in range(7)],
        'portada': [{'puesto': 1, 'empresa': 'P', 'accion': 'a', 'calculado': '2026-11-26'}],
        'nm_dup': 0, 'nm_max': 62,
    }
    txt, n = armar(d, hoy)
    # 15 ganadas sin entregar: la cabecera dice 15 y entre líneas y «+N más» suman 15
    d15 = dict(d, ganadas=[{'numero': f'NM{i}', 'cliente': 'x', 'despacho': '', 'entrega': '', 'transporte': 'x', 'domicilio': 'y'} for i in range(15)])
    t15, _ = armar(d15, hoy)
    mala = dict(d, cotizaciones=d['cotizaciones'] + [{'numero': 'NM48', 'cliente': 'Swiss', 'estado': 'enviada', 'fecha': '2026-11-03', 'vence': '2026-09-26'}])
    tm, nm = armar(mala, hoy)
    lfab = ['IMPORTANTE: x', 'ARRANQUE LISTO', 'CRM actualizado: 3', 'CADENA loki: PASA', 'basura de portada']
    fl, ff = filtrar_abrir('\n'.join(lfab))
    fl2, ff2 = filtrar_abrir('ARRANQUE NO_LISTO\nFALLA L10 el script no es el del repo')
    casos = [
        ('vencida D02', n['vencidas'] == 1 and 'NM10' in txt),
        ('D02 propone pasar 5 días, no perdida', 'se pasan 5 días → 2026-12-02' in txt and 'nuevo estado o perdida' not in txt),
        ('propuesta de prórroga armada', n['prorroga'] == [{'doc_id': 'd10', 'numero': 'NM10', 'cliente': 'Vencida',
                                                            'vence_actual': '2026-11-20', 'vence_nuevo': '2026-12-02'}]),
        ('vence≥fecha PASA', 'vence≥fecha PASA' in txt and n['malas'] == 0),
        ('vence≥fecha FALLA con NM48', nm['malas'] == 1 and 'vence≥fecha FALLA (NM48 fecha 2026-11-03 vence 2026-09-26)' in tm),
        ('ganadas: cabecera = lista', t15.count('\n  NM') == 12 and '+3 más' in t15 and 'GANADAS SIN ENTREGAR (15)' in t15),
        ('ganadas: 9 muestra 9', n['ganadas'] == 9 and all(f'NM7{i}' in txt for i in range(7))),
        ('abrir: solo controles', fl == ['ARRANQUE LISTO', 'CADENA loki: PASA'] and not ff),
        ('abrir: FALLA para', ff2 and len(fl2) == 2),
        ('revisar hoy', 'REVISAR HOY (1): NM11' in txt),
        ('ganadas: entregada fuera', 'NM40' not in txt),
        ('ganada despachada pide entrega', 'NM52 Despachada · falta entrega' in txt),
        ('ganada sin despacho', 'NM59 Sin despacho · falta transporte, despacho' in txt),
        ('D07 fuera de seguimientos', 'Ajena SA' not in txt),
        ('semana vs atrasados', n['semana'] == 1 and n['atrasados'] == 1),
        ('futuros fuera', 'Futura SA' not in txt),
        ('portada vieja avisada', 'NO ES DE HOY' in txt),
        ('próximo NM', 'Próximo NM: NM63' in txt),
        ('edad Finnegans', 'edad Finnegans AVISO (2026-11-15)' in txt),
        ('corta', len(txt) < 2000),
    ]
    ok = sum(1 for _, b in casos if b)
    for nombre, b in casos:
        if not b:
            print('FALLA ·', nombre)
    print(f'autotest apertura_corta: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    if not a:
        sys.exit(__doc__)
    hoy = a[0]
    D.date.fromisoformat(hoy)
    if '--crm' in a:   # 0.2: arranque en un paso (abrir + apertura)
        i = a.index('--crm')
        origen = a[a.index('--origen') + 1] if '--origen' in a else ORIGEN_CRM
        if abrir(hoy, a[i + 1], origen, '--incremental' in a):
            sys.exit(2)
    texto, n = armar(leer_turso(), hoy)
    print(texto)
    ruta = guardar_prorroga(n['prorroga'], hoy)
    if ruta:
        print(f'PRÓRROGA lista para el «hacelo»: {ruta}')
