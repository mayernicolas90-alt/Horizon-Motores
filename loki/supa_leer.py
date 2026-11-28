"""supa_leer.py 0.1 · Loki lee Supabase (proyecto horizon) SOLO LECTURA · 28/11/2026
Token: Administrador de credenciales de Windows, destino «Loki/Supabase-horizon» (lo guardó Nicolás, bitácora #263).
Va por la API de administración con read_only=true (Supabase corre la consulta en una transacción de solo lectura)
y además acá se rechaza todo lo que no sea una sola consulta SELECT / WITH. No escribe en ninguna base.
Provisorio hasta que exista el rol loki (fase 2): ese token es de la cuenta, por eso la doble compuerta.
Uso: python -I -X utf8 supa_leer.py tablas | apertura | ping | "SELECT ..." | --autotest"""
import ctypes, json, re, sys, urllib.error, urllib.request

VERSION = '0.1'
REF = 'dvmdwmytlqubllchkeii'
URL = f'https://api.supabase.com/v1/projects/{REF}/database/query'
TARGET = 'Loki/Supabase-horizon'
ESCRITURA = r'\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|do|merge|vacuum|comment|lock|refresh|reindex|cluster|security|listen|notify|prepare|execute|import)\b'
ATAJOS = {
    'tablas': "SELECT table_schema AS esquema, table_name AS tabla, table_type AS tipo FROM information_schema.tables "
              "WHERE table_schema NOT IN ('pg_catalog','information_schema','auth','storage','realtime','extensions',"
              "'graphql','graphql_public','pgsodium','pgsodium_masks','vault','supabase_functions','supabase_migrations',"
              "'net','pgbouncer','cron') ORDER BY 1, 2",
    'apertura': 'SELECT apertura FROM apertura.hoy',
    'ping': 'SELECT current_user AS usuario, now() AS hora',
}


def token():
    import ctypes.wintypes as W

    class CRED(ctypes.Structure):
        _fields_ = [('Flags', W.DWORD), ('Type', W.DWORD), ('TargetName', W.LPWSTR), ('Comment', W.LPWSTR),
                    ('LastWritten', W.FILETIME), ('CredentialBlobSize', W.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_char)),
                    ('Persist', W.DWORD), ('AttributeCount', W.DWORD), ('Attributes', ctypes.c_void_p),
                    ('TargetAlias', W.LPWSTR), ('UserName', W.LPWSTR)]
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    p = ctypes.POINTER(CRED)()
    if not adv.CredReadW(TARGET, 1, 0, ctypes.byref(p)):
        sys.exit('FALLA: no está la credencial ' + TARGET)
    try:
        crudo = ctypes.string_at(p.contents.CredentialBlob, p.contents.CredentialBlobSize)
    finally:
        adv.CredFree(p)
    # cmdkey guarda UTF-16; una ficha con getpass puede guardar UTF-8. Se aceptan las dos.
    t = crudo.decode('utf-16-le') if len(crudo) > 1 and crudo[1:2] == b'\x00' else crudo.decode()
    return t.strip()


def solo_lectura(sql):
    s = sql.strip().rstrip(';').strip()
    sin_textos = re.sub(r"'(?:[^']|'')*'", "''", s)          # lo que va entre comillas no cuenta
    if ';' in sin_textos or not re.match(r'^(select|with)\b', s, re.I):
        sys.exit('RECHAZADO: supa_leer solo acepta una consulta SELECT / WITH')
    if re.search(ESCRITURA, sin_textos, re.I):
        sys.exit('RECHAZADO: la consulta contiene una palabra de escritura')
    return s


def consulta(sql):
    body = json.dumps({'query': solo_lectura(sql), 'read_only': True}).encode()
    rq = urllib.request.Request(URL, data=body, method='POST', headers={
        'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/json', 'User-Agent': 'loki-supa-leer/' + VERSION})
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get('message', '')
        except Exception:
            msg = ''
        sys.exit(f'FALLA HTTP {e.code}: {msg}'.strip())
    except urllib.error.URLError as e:
        sys.exit(f'FALLA de red: {e.reason}')


def autotest():
    """Sin red ni token: solo la compuerta de solo lectura."""
    def pasa(sql):
        try:
            solo_lectura(sql); return True
        except SystemExit:
            return False
    casos = [
        ('SELECT acepta', pasa('SELECT * FROM comercial.cotizacion')),
        ('WITH acepta', pasa('WITH x AS (SELECT 1) SELECT * FROM x')),
        ('punto y coma final acepta', pasa('SELECT 1;')),
        ('atajo apertura acepta', pasa(ATAJOS['apertura'])),
        ('atajo tablas acepta', pasa(ATAJOS['tablas'])),
        ('palabra de escritura entre comillas acepta', pasa("SELECT * FROM control.registro WHERE accion = 'update'")),
        ('punto y coma entre comillas acepta', pasa("SELECT 'a;b'")),
        ('DELETE rechaza', not pasa('DELETE FROM comercial.cotizacion')),
        ('INSERT rechaza', not pasa('INSERT INTO x VALUES (1)')),
        ('dos sentencias rechaza', not pasa('SELECT 1; DROP TABLE x')),
        ('UPDATE dentro de WITH rechaza', not pasa('WITH x AS (SELECT 1) UPDATE y SET a = 1')),
        ('DELETE dentro de WITH rechaza', not pasa('WITH b AS (DELETE FROM y RETURNING *) SELECT * FROM b')),
        ('TRUNCATE rechaza', not pasa('TRUNCATE x')),
        ('GRANT rechaza', not pasa('GRANT ALL ON x TO loki')),
        ('SELECT FOR UPDATE rechaza', not pasa('SELECT * FROM x FOR UPDATE')),
        ('DO rechaza', not pasa("DO $$ BEGIN PERFORM 1; END $$")),
        ('vacía rechaza', not pasa('   ')),
    ]
    mal = [n for n, ok in casos if not ok]
    for n, ok in casos:
        print(('PASA ' if ok else 'FALLA') + ' · ' + n)
    print(f'autotest supa_leer {VERSION}: {len(casos) - len(mal)}/{len(casos)} ' + ('PASA' if not mal else 'FALLA'))
    sys.exit(1 if mal else 0)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['--autotest']:
        autotest()
    if not a:
        sys.exit(__doc__)
    filas = consulta(ATAJOS.get(a[0], a[0]))
    if a[0] == 'apertura' and filas:
        v = filas[0].get('apertura')
        print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1))
    else:
        for f in filas:
            print(json.dumps(f, ensure_ascii=False, default=str))
