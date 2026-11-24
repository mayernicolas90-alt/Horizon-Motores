#!/usr/bin/env python3
"""puntaje.py 0.1 · motor Puntaje del datacenter (24/11/2026, DEC-1124a/b). Solo biblioteca estándar.

Puntaje de cierre (0-100) de cada ficha del CRM, con las reglas del puntaje V143 de la página del CRM (prioInfo), calculado en
Turso a partir de la copia del CRM (tabla crm: oportunidades, cotizaciones, muestras con su documento completo).
Dos cambios respecto del CRM, por diseño del datacenter:
  · la recompra («le toca» +14, «atrasado» +8) sale del motor Recompra (rec_cliente, compras limpias) y no de la facturación cruda;
  · las cuentas que no se trabajan salen del motor Cuentas (cue_cuentas: otro vendedor, no prospectar, archivada, unificada).
Guarda dos puntajes: «s» (igual que el CRM, el monto suma hasta +20) y «s_sin_monto» (el monto queda aparte como valor_en_juego),
para que la Portada use el que Nicolás elija. También guarda si la ficha es elegible hoy (misma regla que el Sales Engine).

Uso (python3 -I): puntaje.py --contrato · puntaje.py --autotest · puntaje.py correr [--loki ruta] [--hoy AAAA-MM-DD] · puntaje.py simular
"""
import datetime as D, importlib.util, json, math, os, re, statistics, sys

VERSION = 'puntaje 0.2 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
CONTRATO = {'id': 'puntaje', 'nombre': 'Puntaje', 'disparo': 'loki', 'lee': ['crm', 'rec_cliente', 'cue_cuentas'], 'escribe': ['pun_fichas'],
            'que_hace': 'Puntaje de cierre 0-100 por ficha (reglas V143 del CRM) con recompra limpia y cuentas excluidas; monto aparte.'}
COLS = ['crm_id', 'cuit', 'empresa', 'etapa', 'elegible', 's', 's_sin_monto', 'valor_en_juego', 'nivel', 'objetivo', 'funding', 'evidencia',
        'recompra', 'razones', 'excluida', 'motivo_exclusion', 'calculado']
OPEN = {'prospecto', 'contactado', 'calificado', 'cotizado', 'negociacion'}
STAGE = {'negociacion': 22, 'cotizado': 15, 'calificado': 9, 'contactado': 6, 'prospecto': 2, 'ganado': 9, 'pausa': 0}
LIMITE = {'negociacion': 3, 'cotizado': 5, 'calificado': 7, 'contactado': 10, 'prospecto': 14, 'ganado': 30, 'pausa': 30}
MACTIVA = {'pedida', 'sin_retirar', 'enviada', 'prueba'}
SENT = {'enviada', 'borrador'}
FUERA = {'rechazada', 'cancelada', 'perdida', 'entregada'}
INTERNA = re.compile(r'horizon trading|sur technology|presupuesto horizon', re.I)


def dig(s):
    return re.sub(r'\D', '', str(s or ''))


def dn(f):
    return D.date.fromisoformat(f[:10]).toordinal()


def fmtk(v):
    return f'{round(v / 1000)}k' if v >= 1000 else str(round(v))


def calcular(fichas, cots, mues, rec, cue, hoy):
    """fichas/cots/mues: documentos del CRM (con 'id') · rec: {cuit: estado} · cue: {crm_id o cuit: (trabajar, motivo)}."""
    t = hoy
    nombres = {o['id']: o.get('empresa') or '' for o in fichas}
    valida = lambda c: not c.get('archivada') and not INTERNA.search(str(nombres.get(c.get('oportunidadId'), '') or c.get('cliente') or ''))
    gano = lambda c: str(c.get('estado') or '').lower() == 'aceptada' or bool((c.get('hz_operacion') or {}).get('pedidoConfirmado'))
    por_op = {}
    for c in cots:
        if valida(c):
            por_op.setdefault(c.get('oportunidadId'), []).append(c)
    activas = lambda o: [c for c in por_op.get(o['id'], []) if str(c.get('estado') or '').lower() not in FUERA
                         and not all((c.get('hz_operacion') or {}).get(k) == 'confirmado' for k in ('pago', 'despacho', 'entrega'))]
    muestras = lambda o: [m for m in mues if m.get('oportunidadId') == o['id'] and m.get('estado') in MACTIVA]
    cumplida = lambda o: bool(o.get('proximaFecha') and o.get('ultimoContacto') and o['ultimoContacto'] >= o['proximaFecha'])
    def ultimo_contacto(o):
        lc = o.get('ultimoContacto') or ''
        for e in o.get('historial') or []:
            if re.match(r'^(WhatsApp enviado|Contacto registrado)', str(e.get('txt') or '')):
                lc = max(lc, str(e.get('t') or '')[:10])
        return lc
    def recurrente(o):
        """Reposición estimada por cotizaciones ganadas (hz3Recurring del CRM)."""
        cl = {}
        for c in por_op.get(o['id'], []):
            if c.get('estado') != 'aceptada':
                continue
            f = str(c.get('fechaGanada') or c.get('fecha') or '')[:10]
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', f):
                continue
            for i in (c.get('items') or [{'articulo': c.get('familia') or o.get('productos'), 'cantidad': 0}]):
                tx = ' '.join(str(x or '') for x in (i.get('articulo'), i.get('descripcion'), c.get('familia'))).upper()
                m = re.search(r'(?:HG|EG)\d{4}[A-Z0-9-]*|AN5506[-A-Z0-9]*|(?:ONT|ONU).*?(?:WIFI ?6|GPON|XGS)', tx)
                k = m.group(0) if m else 'ONT / ONU' if re.search('ONT|ONU', tx) else 'CABLE FIBRA' if re.search('ADSS|ASU|DROP|CABLE', tx) else 'CONECTORES' if 'CONECTOR' in tx else str(c.get('familia') or i.get('articulo') or 'OTROS').upper()
                cl.setdefault(k, set()).add(f)
        out = []
        for fam, fs in cl.items():
            fs = sorted(fs)
            if len(fs) < 2:
                continue
            gaps = sorted(g for g in (dn(b) - dn(a) for a, b in zip(fs, fs[1:])) if g > 0)
            if not gaps:
                continue
            cy = gaps[len(gaps) // 2]
            if 7 <= cy <= 180:
                out.append((fam, dn(fs[-1]) + cy - dn(t), len(fs)))
        return [x for x in out if -7 <= x[1] <= 7]
    filas = []
    for o in fichas:
        if o.get('archivada'):
            continue
        cuit = dig(o.get('facturacionId') or o.get('cuit'))
        trabajar, motivo = cue.get(o['id'], cue.get(cuit, (1, '')))
        estado_rec, global_rec = rec.get(cuit, (None, None))
        # 0.2: le toca / atrasado por SKU (reglas v3.1) o por ciclo global del cliente (patrón de compra del CRM)
        toca = estado_rec == 'Le toca' or global_rec == 'toca'
        atrasado = not toca and (estado_rec == 'Atrasado' or global_rec == 'atrasado')
        due = toca or atrasado
        base = dict(crm_id=o['id'], cuit=cuit or None, empresa=o.get('empresa') or '', etapa=o.get('etapa') or '', calculado=t,
                    recompra=estado_rec, excluida=int(not trabajar), motivo_exclusion=motivo or None)
        act = activas(o)
        decision = bool(act) and all(c.get('estado') == 'espera_decision' for c in act if c.get('estado') != 'aceptada') and \
            any(c.get('estado') != 'aceptada' for c in act)
        nuevas = any(c.get('estado') in ('borrador', 'enviada') and not gano(c) for c in act)
        repurchase = o.get('etapa') == 'ganado' and (nuevas or (o.get('proximaFecha') and o['proximaFecha'] <= t and not cumplida(o)
                                                               and re.search(r'recompra|reposici[oó]n|nuevo pedido|nueva necesidad|ampliaci[oó]n', str(o.get('proximaAccion') or ''), re.I)))
        if not trabajar or decision or o.get('noProspectar') == 'si' or o.get('etapa') == 'perdido' or (o.get('etapa') == 'ganado' and not repurchase and not due):
            filas.append(dict(base, elegible=0, s=None, s_sin_monto=None, valor_en_juego=None, nivel=None, objetivo=None, funding=None, evidencia=0,
                              razones=json.dumps(['Espera de decisión del cliente' if decision else 'Fuera del puntaje'], ensure_ascii=False)))
            continue
        quotes = [c for c in act if c.get('estado') in SENT and not gano(c)]
        sample = muestras(o)
        v = sum(float(c.get('total') or 0) for c in quotes)
        raw = ' '.join(str(x) for x in (o.get('proximaAccion'), o.get('notas')) if x)
        fin = str(o.get('financiacionEstado') or '').strip().lower()
        estados_q = [str(c.get('estado') or '') for c in por_op.get(o['id'], [])]
        funding = ('confirmada' if fin == 'con_fondos' else 'pendiente' if fin == 'en_aprobacion' else 'sin_fondos' if fin == 'sin_fondos'
                   else 'sin_fondos' if 'sin_fondos' in estados_q else 'pendiente' if 'espera_aprobacion' in estados_q else 'sin_definir')
        R, s, m_pts = [], STAGE.get(o.get('etapa'), 0), 0
        if quotes:
            s += 19; R.append('Cotización enviada')
        elif sample:
            s += 6; R.append('Muestra técnica en evaluación')
        if v > 0:
            m_pts = min(12, round(3 * math.log10(1 + v))) + (min(8, round(4 * math.log10(v / 10000))) if v > 10000 else 0)
            s += m_pts; R.append('Valor en juego: USD ' + fmtk(v))
        elif float(o.get('monto') or 0) > 0:
            R.append('Monto estimado sin cotización enviada')
        if o.get('compromisoCompra') == 'si':
            s += 18; R.append('Compromiso de compra confirmado')
        if o.get('decisor') == 'si':
            s += 9; R.append('Decisor identificado')
        elif o.get('etapa') in ('cotizado', 'negociacion'):
            R.append('Confirmar decisor')
        if sample or re.search(r'homologaci[oó]n|prueba t[eé]cnica|compatibilidad validada|evaluaci[oó]n t[eé]cnica', raw, re.I):
            s += 7; R.append('Validación técnica en curso')
        if str(o.get('proximaAccion') or '').strip():
            s += 5; R.append('Acción comercial definida')
        elif o.get('etapa') in OPEN:
            R.append('Definir siguiente acción')
        pf = o.get('proximaFecha')
        if pf and pf <= t and not cumplida(o):
            s += min(5, 3 + min(2, max(0, dn(t) - dn(pf)))); R.append('Paso vencido' if pf < t else 'Paso para hoy')
        rep = recurrente(o)
        if rep:
            s += min(10, 5 + len(rep) * 2); R.append('Reposición estimada: ' + rep[0][0])
        plazo = str(o.get('plazo') or '').lower().strip()
        if plazo in ('30', 'mes', 'este mes', 'inmediato', '30 días', '30 dias'):
            s += 8; R.append('Compra declarada: 30 días')
        elif plazo in ('60', '60 días', '60 dias'):
            s += 5; R.append('Compra declarada: 60 días')
        elif plazo in ('90', 'trimestre', 'este trimestre', '90 días', '90 dias'):
            s += 3; R.append('Compra declarada: 90 días')
        s += {'confirmada': 20, 'pendiente': -12, 'sin_fondos': -45}.get(funding, -6)
        R.append({'confirmada': 'Fondos confirmados', 'pendiente': 'Financiación en aprobación', 'sin_fondos': 'SIN FONDOS'}.get(funding, 'Fondos sin confirmar'))
        if o.get('etapa') == 'pausa':
            s -= 15
        if not o.get('contacto') and not o.get('telefono') and not o.get('email'):
            s -= 8; R.append('Sin contacto verificable')
        if toca:
            s += 14; R.append('Le toca reponer (Recompra)')
        elif atrasado:
            s += 8; R.append('Atrasado en su ciclo de compra (Recompra)')
        evidencia = bool(quotes) or o.get('compromisoCompra') == 'si' or bool(sample) or due
        def tope(x):
            if not evidencia:
                x = min(x, 28)
            if funding == 'sin_fondos':
                x = min(x, 12)
            return max(0, min(100, round(x)))
        if not evidencia:
            R.append('Sin evidencia activa de compra')
        s1, s0 = tope(s), tope(s - m_pts)
        lc = ultimo_contacto(o)
        dias = max(0, dn(t) - dn(lc)) if lc else None
        if dias is None:
            R.append('Nunca contactado')
        elif dias > LIMITE.get(o.get('etapa'), 14):
            R.append(f'{dias} días sin contacto')
        obj = ('financiacion' if funding == 'sin_fondos' else 'recompra' if due and not quotes else 'muestra' if sample else 'cierre'
               if o.get('etapa') == 'negociacion' else 'seguimiento' if quotes else 'recompra' if repurchase else 'desarrollar')
        if obj == 'desarrollar':
            obj = 'primer_contacto' if (o.get('etapa') == 'prospecto' or dias is None) else 'reactivar'
        elegible = (o.get('etapa') in OPEN or (o.get('etapa') == 'ganado' and repurchase) or (o.get('etapa') in ('ganado', 'pausa') and due)) \
            and not (pf and pf > t and not cumplida(o))
        filas.append(dict(base, elegible=int(bool(elegible)), s=s1, s_sin_monto=s0, valor_en_juego=round(v, 2),
                          nivel='alta' if s1 >= 60 else 'media' if s1 >= 35 else 'baja', objetivo=obj, funding=funding,
                          evidencia=int(bool(evidencia)), razones=json.dumps(R, ensure_ascii=False)))
    return filas


def loki(ruta=None):
    ruta = ruta or os.path.join(AQUI, 'loki_sql.py')
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def leer(db):
    cols, filas = db.run([("SELECT coleccion, id, data FROM crm WHERE coleccion IN ('oportunidades','cotizaciones','muestras')", [])])[0]
    docs = {'oportunidades': [], 'cotizaciones': [], 'muestras': []}
    for col, i, data in filas:
        d = json.loads(data or '{}')
        d['id'] = i
        docs[col].append(d)
    rec = {r[0]: (r[1], r[2]) for r in db.run([('SELECT cuit, estado, estado_global FROM rec_cliente', [])])[0][1]}
    cue = {}
    for clave, cuit, crm_id, trabajar, motivo in db.run([('SELECT clave, cuit, crm_id, trabajar, motivo FROM cue_cuentas', [])])[0][1]:
        if crm_id:
            cue[crm_id] = (trabajar, motivo)
        if cuit:
            cue.setdefault(cuit, (trabajar, motivo))
    return docs['oportunidades'], docs['cotizaciones'], docs['muestras'], rec, cue


def escribir(db, filas):
    db.run([('DROP TABLE IF EXISTS pun_fichas', []), ('CREATE TABLE pun_fichas(' + ', '.join(COLS) + ')', [])]
           + [('INSERT INTO pun_fichas VALUES(' + ','.join('?' * len(COLS)) + ')', [f[c] for c in COLS]) for f in filas])


def resumen(filas):
    p = [f for f in filas if f['s'] is not None]
    return {'fichas': len(filas), 'con_puntaje': len(p), 'elegibles': sum(f['elegible'] for f in filas), 'excluidas': sum(f['excluida'] for f in filas),
            'alta': sum(f['nivel'] == 'alta' for f in p), 'media': sum(f['nivel'] == 'media' for f in p)}


# ---------------------------------------------------------------- autotest (sin datos reales)
def autotest():
    hoy = '2026-11-24'
    O = lambda i, **k: dict(dict(id=i, empresa='Empresa ' + i, cuit='30-' + i, etapa='cotizado', contacto='Ana', proximaAccion='Llamar',
                                 proximaFecha='2026-11-20'), **k)
    C = lambda op, total, estado='enviada', **k: dict(dict(id='c' + op + str(total), oportunidadId=op, total=total, estado=estado, fecha='2026-11-01'), **k)
    fichas = [O('1'), O('2', financiacionEstado='sin_fondos'), O('3', etapa='ganado', proximaAccion='', proximaFecha=''), O('4'), O('5', etapa='ganado'),
              O('6', archivada=True), O('7', proximaFecha='2026-12-10'), O('8'), O('9', empresa='Horizon Trading S.A.')]
    cots = [C('1', 62000), C('2', 5000), C('4', 15000, 'espera_decision'), C('7', 1000), C('9', 9999)]
    f = {x['crm_id']: x for x in calcular(fichas, cots, [], {'303': ('Le toca', None), '305': (None, 'atrasado')}, {'8': (0, 'D07: otro vendedor')}, hoy)}
    m = min(12, round(3 * math.log10(62001))) + min(8, round(4 * math.log10(6.2)))
    casos = [
        ('cotización enviada suma 19 y el monto hasta 20', f['1']['s'] - f['1']['s_sin_monto'] == m and f['1']['valor_en_juego'] == 62000),
        ('puntaje V143: etapa 15 + cotización 19 + monto + acción 5 + paso vencido 5 − fondos 6', f['1']['s'] == 15 + 19 + m + 5 + 5 - 6),
        ('sin fondos: tope 12', f['2']['s'] <= 12 and f['2']['funding'] == 'sin_fondos'),
        ('ganado al que le toca reponer (Recompra) entra y suma 14', f['3']['s'] is not None and 'Le toca reponer (Recompra)' in json.loads(f['3']['razones'])),
        ('espera de decisión del cliente: fuera del puntaje', f['4']['s'] is None and f['4']['elegible'] == 0),
        ('ganado atrasado en su ciclo global: entra por recompra', f['5']['s'] is not None and f['5']['elegible'] == 1),
        ('ficha archivada: no se evalúa', '6' not in f),
        ('gestión agendada a futuro: no elegible hoy', f['7']['elegible'] == 0 and f['7']['s'] is not None),
        ('cuenta que no se trabaja (Cuentas): sin puntaje y excluida', f['8']['s'] is None and f['8']['excluida'] == 1),
        ('cotización interna (Horizon Trading) no cuenta', 'Cotización enviada' not in json.loads(f['9']['razones'])),
    ]
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    ok = sum(1 for _, x in casos if x)
    print(f'autotest puntaje: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    hoy = a[a.index('--hoy') + 1] if '--hoy' in a else D.datetime.now(D.timezone(D.timedelta(hours=-3))).date().isoformat()
    if '--autotest' in a:
        sys.exit(autotest())
    if '--contrato' in a:
        print(json.dumps(dict(CONTRATO, version=VERSION), ensure_ascii=False))
        sys.exit(0)
    if a[:1] in (['correr'], ['simular']):
        db = loki(a[a.index('--loki') + 1] if '--loki' in a else None).conectar()
        filas = calcular(*leer(db), hoy)
        if a[0] == 'correr':
            escribir(db, filas)
        db.close()
        if a[0] == 'simular':
            print(json.dumps(sorted([x for x in filas if x['s'] is not None], key=lambda x: -x['s'])[:15], ensure_ascii=False))
        print('RESUMEN ' + json.dumps(resumen(filas), ensure_ascii=False))
        sys.exit(0)
    print(__doc__)
