#!/usr/bin/env python3
"""espejo.py 0.1 · 28/11/2026 · conecta los motores de Loki a Supabase (Nicolás 28/11: «conectá tus motores a Supabase»).

Los motores siguen corriendo como hoy (dc.py, Turso). Al final, el Espejo publica en Supabase las tablas que cada motor
escribe según su contrato, así Supabase queda al día sin que nadie las copie a mano:
  1. solo publica motores cuya última corrida en dc_corridas está OK y con auditor PASA/AVISO (DEC-1124c);
  2. por cada tabla: arma la tabla nueva en una transacción (borrar + insertar con json_populate_recordset), agrega las
     columnas de la mudanza (dueno='loki', mudado=hoy, cuit11 y foto si existen) y deja una fila en control.registro;
  3. después vuelve a leer y compara fila por fila con Turso: si no queda igual, lo dice (FALLA) y no sigue.
Sin --escribir solo compara y muestra qué cambiaría (no toca nada).

Mientras no exista el acceso del rol `loki`, escribe con el token de cuenta de la API de administración (lo inyecta el
proxy del entorno; nunca está en el código). Queda anotado en el registro: via=token de cuenta (provisorio).

Uso (python3 -I):  espejo.py correr [--escribir] [--solo MOTOR] [--loki RUTA] · espejo.py --contrato · espejo.py --autotest
"""
import datetime as D, hashlib, importlib.util, json, math, os, re, sys, urllib.error, urllib.request, collections

VERSION = 'espejo 0.3 · 2026-11-28'
AQUI = os.path.dirname(os.path.abspath(__file__))
PROYECTO = 'dvmdwmytlqubllchkeii'
API = f'https://api.supabase.com/v1/projects/{PROYECTO}/database/query'
# tabla de Turso (contrato del motor) → tabla de Supabase (nota ar de la mudanza)
DESTINO = {'rec_cliente': 'motores.recompra_cliente', 'rec_sku': 'motores.recompra_sku', 'pun_fichas': 'motores.puntaje',
           'por_dia': 'motores.portada', 'cue_cuentas': 'clientes.cuenta', 'cue_cuit': 'clientes.cuit', 'cue_marca': 'clientes.marca'}
# 0.2 (28/11, Nicolás: «empezá a operar de Supabase»): tablas que escribe Loki mismo (no un motor). Se publican en cada corrida
# para que Supabase tenga el hilo y el conocimiento al día. Con clave primaria se actualiza por clave y se conservan las columnas
# que agregó otro (por ejemplo vendedor en comercial.cotizacion). La copia del CRM (comercial.*) la hace el PM: no se toca.
DIRECTAS = {'bitacora': 'operacion.bitacora', 'tema': 'operacion.tema', 'tema_evento': 'operacion.tema_evento',
            'continuidad': 'operacion.continuidad', 'k_regla': 'conocimiento.regla', 'k_decision': 'conocimiento.decision',
            'k_preferencia': 'conocimiento.preferencia', 'k_procedimiento': 'conocimiento.procedimiento', 'k_motor': 'conocimiento.motor',
            'k_fuente': 'conocimiento.fuente', 'k_documento': 'conocimiento.documento', 'cliente_alias': 'clientes.alias'}
# limpia_* (Limpieza) no tienen destino hasta el duelo de la capa limpia con el Finnegans del PM: se informan y no se publican.


def contrato_propio():
    return {'id': 'espejo', 'nombre': 'Espejo a Supabase', 'version': VERSION, 'disparo': 'despues', 'lee': list(DESTINO),
            'escribe': [], 'que_hace': 'Publica en Supabase las salidas de los motores con auditor PASA y verifica fila por fila.'}


# ------------------------------------------------------------------ Supabase (API de administración)
CRED_PC = 'Loki/Supabase-horizon'      # Administrador de credenciales de Windows (bitácora #263)


def token_pc():
    """En la PC el token sale del Administrador de credenciales; en la nube lo pone el proxy (devuelve None)."""
    if os.name != 'nt':
        return None
    import ctypes, ctypes.wintypes as W

    class CRED(ctypes.Structure):
        _fields_ = [('Flags', W.DWORD), ('Type', W.DWORD), ('TargetName', W.LPWSTR), ('Comment', W.LPWSTR),
                    ('LastWritten', W.FILETIME), ('CredentialBlobSize', W.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_char)),
                    ('Persist', W.DWORD), ('AttributeCount', W.DWORD), ('Attributes', ctypes.c_void_p),
                    ('TargetAlias', W.LPWSTR), ('UserName', W.LPWSTR)]
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    p = ctypes.POINTER(CRED)()
    if not adv.CredReadW(CRED_PC, 1, 0, ctypes.byref(p)):
        raise SystemExit(f'FALLA: no está la credencial «{CRED_PC}» en el Administrador de credenciales')
    try:
        return ctypes.string_at(p.contents.CredentialBlob, p.contents.CredentialBlobSize).decode().strip()
    finally:
        adv.CredFree(p)


_TOK = []


def supa(sql, solo_lectura=True):
    body = json.dumps({'query': sql, 'read_only': solo_lectura}).encode()
    if not _TOK:
        _TOK.append(token_pc())
    hdr = {'Content-Type': 'application/json'}
    if _TOK[0]:
        hdr['Authorization'] = 'Bearer ' + _TOK[0]
    import time
    for intento in range(6):   # 0.2.1: la API limita pedidos por minuto (429): espera y reintenta, sin repetir escrituras a medias
        rq = urllib.request.Request(API, data=body, headers=hdr)
        try:
            with urllib.request.urlopen(rq, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento < 5:
                time.sleep(5 * (intento + 1))
                continue
            raise RuntimeError(f'Supabase {e.code}: {e.read()[:400].decode(errors="replace")}') from None


def lit(s):
    """Texto como literal de Postgres con dollar-quoting que no choca con el contenido."""
    tag = 'j' + hashlib.sha1(s.encode()).hexdigest()[:8]
    return f'${tag}${s}${tag}$'


def columnas_supa(tabla):
    esq, t = tabla.split('.')
    return [r['column_name'] for r in supa(
        f"SELECT column_name FROM information_schema.columns WHERE table_schema='{esq}' AND table_name='{t}' ORDER BY ordinal_position")]


def clave_primaria(tabla):
    esq, t = tabla.split('.')
    r = supa(f"SELECT a.attname FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
             f"JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=ANY(i.indkey) WHERE i.indisprimary AND n.nspname='{esq}' AND c.relname='{t}'")
    return [x['attname'] for x in r] or None


def cuit11(v):
    d = re.sub(r'\D', '', str(v or ''))
    return d if len(d) == 11 else None


def sql_publicar(tabla, filas, cols_destino, motor, version, hoy, pk=None):
    extra = {}
    if 'dueno' in cols_destino:
        extra['dueno'] = 'loki'
    if 'mudado' in cols_destino:
        extra['mudado'] = hoy
    if 'foto' in cols_destino:
        extra['foto'] = f'motor {motor} {hoy} (espejo), fuente Turso hasta el corte'
    datos = []
    for f in filas:
        g = {k: v for k, v in f.items() if k in cols_destino}
        g.update(extra)
        if 'cuit11' in cols_destino:
            g['cuit11'] = cuit11(f.get('cuit'))
        datos.append(g)
    js = json.dumps(datos, ensure_ascii=False, default=str)
    h = hashlib.sha256(js.encode()).hexdigest()[:16]
    det = json.dumps({'via': 'rol loki (SET LOCAL ROLE, permisos nota bl)', 'origen': 'Turso horizon-nicom90', 'espejo': VERSION},
                     ensure_ascii=False)
    if pk:   # 0.2: por clave; las columnas que no vienen de Turso (las agregó otro) no se tocan
        cols = sorted({k for g in datos for k in g})
        sets = ', '.join(f'"{c}"=EXCLUDED."{c}"' for c in cols if c not in pk)
        claves = ', '.join(f'"{c}"' for c in pk)
        cuerpo = (f"DELETE FROM {tabla} t WHERE ({', '.join('t.' + chr(34) + c + chr(34) for c in pk)}) NOT IN "
                  f"(SELECT {claves} FROM json_populate_recordset(NULL::{tabla}, {lit(js)}::json)); "
                  f"INSERT INTO {tabla} ({', '.join(chr(34) + c + chr(34) for c in cols)}) SELECT {', '.join(chr(34) + c + chr(34) for c in cols)} "
                  f"FROM json_populate_recordset(NULL::{tabla}, {lit(js)}::json) ON CONFLICT ({claves}) DO UPDATE SET {sets}; ")
    else:
        cuerpo = (f"DELETE FROM {tabla}; "
                  f"INSERT INTO {tabla} SELECT * FROM json_populate_recordset(NULL::{tabla}, {lit(js)}::json); ")
    return h, (f"BEGIN; SET LOCAL ROLE loki; {cuerpo}"
               f"INSERT INTO control.registro(cuando, agente, tabla, operacion, motor, version, hash_entrada, filas, detalle) "
               f"VALUES (now(), 'loki', '{tabla}', 'carga', '{motor}', {lit(version)}, '{h}', {len(datos)}, {lit(det)}::jsonb); COMMIT;")


# ------------------------------------------------------------------ comparación (misma regla que auditar_mudanza.py)
def norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return ('n', float(v))
    if isinstance(v, (int, float)):
        return ('n', round(float(v), 6))
    if isinstance(v, (dict, list)):
        return ('j', json.dumps(v, sort_keys=True, ensure_ascii=False))
    s = str(v)
    try:
        f = float(s)
        if math.isfinite(f) and s.strip() == s and s:
            return ('n', round(f, 6))
    except ValueError:
        pass
    if s[:1] in '[{':
        try:
            return ('j', json.dumps(json.loads(s), sort_keys=True, ensure_ascii=False))
        except ValueError:
            pass
    return ('s', s)


def comparar(a, b, cols):
    k = lambda r: tuple(json.dumps(norm(r.get(c)), ensure_ascii=False) for c in cols)
    A, B = collections.Counter(map(k, a)), collections.Counter(map(k, b))
    return sum((A & B).values()), sum((A - B).values()), sum((B - A).values())


# ------------------------------------------------------------------ corrida
def cargar_loki(ruta):
    ruta = ruta or os.path.join(AQUI, 'loki_sql.py')
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def correr(escribir=False, solo=None, loki_ruta=None):
    L = cargar_loki(loki_ruta)
    db = L.conectar()
    q = lambda s, a=(): [dict(zip(c, f)) for c, f in [db.run([(s, list(a))])[0]]][0] if False else \
        (lambda r: [dict(zip(r[0], x)) for x in r[1]])(db.run([(s, list(a))])[0])
    hoy = D.date.today().isoformat()
    motores = q("SELECT m.id, m.version, m.escribe, (SELECT c.estado||'|'||COALESCE(c.auditor,'') FROM dc_corridas c WHERE c.motor=m.id "
                "ORDER BY c.id DESC LIMIT 1) ult FROM dc_motores m")
    salida, malas = [], 0
    for m in motores:
        if solo and m['id'] != solo:
            continue
        est, aud = (m['ult'] or '|').split('|')
        for t in json.loads(m['escribe'] or '[]'):
            if t not in DESTINO:
                salida.append((m['id'], t, '—', 'SIN DESTINO', 'queda en Turso (duelo de la capa limpia)' if t.startswith('limpia') else 'sin tabla en Supabase'))
                continue
            dest = DESTINO[t]
            if est != 'OK' or aud not in ('PASA', 'AVISO'):
                salida.append((m['id'], t, dest, 'NO PUBLICA', f'última corrida {est or "—"} / auditor {aud or "—"}'))
                continue
            filas = q(f'SELECT * FROM "{t}"')
            cols_d = columnas_supa(dest)
            comunes = [c for c in (filas[0].keys() if filas else []) if c in cols_d]
            actual = supa(f"SELECT {', '.join(chr(34) + c + chr(34) for c in comunes)} FROM {dest}") if comunes else []
            ig, solo_t, solo_s = comparar(filas, actual, comunes)
            if not solo_t and not solo_s:
                salida.append((m['id'], t, dest, 'AL DÍA', f'{len(filas)} filas iguales'))
                continue
            if not escribir:
                salida.append((m['id'], t, dest, 'CAMBIARÍA', f'{len(filas)} en Turso · {len(actual)} en Supabase · {ig} iguales · {solo_t} nuevas/cambiadas · {solo_s} salen'))
                continue
            h, sql = sql_publicar(dest, filas, cols_d, m['id'], m['version'], hoy)
            supa(sql, solo_lectura=False)
            despues = supa(f"SELECT {', '.join(chr(34) + c + chr(34) for c in comunes)} FROM {dest}")
            ig2, a2, b2 = comparar(filas, despues, comunes)
            ok = not a2 and not b2 and len(despues) == len(filas)
            malas += not ok
            salida.append((m['id'], t, dest, 'PUBLICADO PASA' if ok else 'PUBLICADO FALLA', f'{len(filas)} filas · iguales {ig2} · hash {h}'))
            if not ok:
                break
    for t, dest in ([] if solo or malas else DIRECTAS.items()):
        filas = q(f'SELECT * FROM "{t}"')
        cols_d = columnas_supa(dest)
        comunes = [c for c in (filas[0].keys() if filas else []) if c in cols_d]
        sel = ', '.join(chr(34) + c + chr(34) for c in comunes)
        actual = supa(f'SELECT {sel} FROM {dest}') if comunes else []
        ig, solo_t, solo_s = comparar(filas, actual, comunes)
        if not solo_t and not solo_s:
            salida.append(('loki', t, dest, 'AL DÍA', f'{len(filas)} filas iguales'))
            continue
        if not escribir:
            salida.append(('loki', t, dest, 'CAMBIARÍA', f'{len(filas)} en Turso · {len(actual)} en Supabase · {solo_t} nuevas/cambiadas · {solo_s} salen'))
            continue
        pk = clave_primaria(dest)
        h, sql = sql_publicar(dest, filas, cols_d, 'loki', VERSION, hoy, pk)
        supa(sql, solo_lectura=False)
        despues = supa(f'SELECT {sel} FROM {dest}')
        ig2, a2, b2 = comparar(filas, despues, comunes)
        ok = not a2 and not b2 and len(despues) == len(filas)
        malas += not ok
        salida.append(('loki', t, dest, 'PUBLICADO PASA' if ok else 'PUBLICADO FALLA', f'{len(filas)} filas · {solo_t} nuevas/cambiadas · hash {h}'))
        if not ok:
            break
    db.close()
    print(f'{VERSION} · ' + ('ESCRIBE' if escribir else 'solo compara (sin --escribir)'))
    for x in salida:
        print(f'  {x[0]:9} {x[1]:13} → {x[2]:26} {x[3]:15} {x[4]}')
    print('RESUMEN ' + json.dumps({'publicadas': sum(1 for x in salida if x[3].startswith('PUBLICADO')), 'falla': malas}))
    return 1 if malas else 0


def autotest():
    casos = []
    h, sql = sql_publicar('motores.portada', [{'puesto': 1, 'empresa': "O'Brien $$x$$", 'cuit': '30-71449817-3', 'ajena': 1}],
                          ['puesto', 'empresa', 'cuit', 'cuit11', 'dueno', 'mudado', 'foto'], 'portada', 'portada 0.1', '2026-11-28')
    casos.append(('escribe como rol loki (la base impone los permisos)', 'SET LOCAL ROLE loki;' in sql))
    casos.append(('una sola transacción', sql.startswith('BEGIN;') and sql.rstrip().endswith('COMMIT;') and sql.count('DELETE') == 1))
    casos.append(('columna que no existe en Supabase no se manda', '"ajena"' not in sql))
    casos.append(('cuit11 calculado', '"cuit11": "30714498173"' in sql))
    casos.append(('dueño y fecha de mudanza', '"dueno": "loki"' in sql and '"mudado": "2026-11-28"' in sql))
    casos.append(('texto con comillas y $$ no rompe el SQL', "O'Brien $$x$$" in sql and '$j' in sql))
    casos.append(('queda en control.registro', 'INSERT INTO control.registro' in sql and "'carga'" in sql))
    casos.append(('comparación: iguales', comparar([{'a': 1, 'b': '2.50'}], [{'a': '1', 'b': 2.5}], ['a', 'b']) == (1, 0, 0)))
    casos.append(('comparación: distinto', comparar([{'a': 1}], [{'a': 2}], ['a']) == (0, 1, 1)))
    casos.append(('cuit11 de un DNI es nulo', cuit11('16497924') is None))
    casos.append(('limpia_* sin destino', not any(k.startswith('limpia') for k in DESTINO)))
    h2, sq = sql_publicar('comercial.cotizacion', [{'id': 'a', 'numero': 'NM1'}], ['id', 'numero', 'vendedor', 'dueno', 'mudado'],
                          'loki', 'v', '2026-11-28', ['id'])
    casos.append(('con clave: actualiza por clave y conserva columnas ajenas', 'ON CONFLICT ("id") DO UPDATE' in sq and '"vendedor"' not in sq
                  and 'NOT IN' in sq and sq.count('DELETE') == 1))
    casos.append(('el CRM (comercial) no lo publica Loki', not any(v.startswith('comercial.') for v in DIRECTAS.values())))
    ok = sum(1 for _, b in casos if b)
    for n, b in casos:
        print(('  OK    ' if b else '  FALLA ') + n)
    print(f'autotest espejo: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    arg = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
    if '--autotest' in a:
        sys.exit(autotest())
    if '--contrato' in a:
        print(json.dumps(contrato_propio(), ensure_ascii=False))
    elif a[:1] == ['correr']:
        sys.exit(correr('--escribir' in a, arg('--solo'), arg('--loki')))
    else:
        print(__doc__)
