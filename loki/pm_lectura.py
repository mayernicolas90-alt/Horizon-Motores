"""pm_lectura.py 0.1 · Loki lee la base del PM (Turso horizon-msyer) SOLO LECTURA · 24/11/2026
Token: Administrador de credenciales de Windows, destino «Loki/Turso horizon-msyer» (token read-only creado por Nicolás).
Rechaza todo lo que no sea SELECT / WITH / PRAGMA de una sola sentencia. No escribe en ninguna base.
Uso: python -I -X utf8 pm_lectura.py tablas | "SELECT ..." [--json]"""
import ctypes, ctypes.wintypes as W, json, re, sys, urllib.request

URL = 'https://horizon-msyer.aws-sa-east-1.turso.io'
TARGET = 'Loki/Turso horizon-msyer'


class CRED(ctypes.Structure):
    _fields_ = [('Flags', W.DWORD), ('Type', W.DWORD), ('TargetName', W.LPWSTR), ('Comment', W.LPWSTR),
                ('LastWritten', W.FILETIME), ('CredentialBlobSize', W.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_char)),
                ('Persist', W.DWORD), ('AttributeCount', W.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', W.LPWSTR), ('UserName', W.LPWSTR)]


def token():
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    p = ctypes.POINTER(CRED)()
    if not adv.CredReadW(TARGET, 1, 0, ctypes.byref(p)):
        sys.exit('FALLA: no está la credencial ' + TARGET)
    try:
        return ctypes.string_at(p.contents.CredentialBlob, p.contents.CredentialBlobSize).decode()
    finally:
        adv.CredFree(p)


def solo_lectura(sql):
    s = sql.strip().rstrip(';')
    if ';' in s or not re.match(r'^\s*(select|with|pragma)\b', s, re.I):
        sys.exit('RECHAZADO: pm_lectura solo acepta una consulta SELECT / WITH / PRAGMA')
    if re.search(r'\b(insert|update|delete|drop|alter|create|replace|attach|detach|vacuum)\b', s, re.I) and not s.lower().startswith('pragma table_info'):
        sys.exit('RECHAZADO: la consulta contiene una palabra de escritura')
    return s


def consulta(sql):
    body = {'requests': [{'type': 'execute', 'stmt': {'sql': solo_lectura(sql)}}, {'type': 'close'}]}
    rq = urllib.request.Request(URL + '/v2/pipeline', data=json.dumps(body).encode(),
                                headers={'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/json'})
    with urllib.request.urlopen(rq, timeout=60) as r:
        out = json.load(r)
    res = out['results'][0]
    if res.get('type') == 'error':
        sys.exit('SQL: ' + res['error'].get('message', str(res['error'])))
    rs = res['response']['result']
    cols = [c['name'] for c in rs['cols']]
    return [{c: (v.get('value') if isinstance(v, dict) else v) for c, v in zip(cols, fila)} for fila in rs['rows']]


def autotest():
    """Sin red ni token: solo la compuerta de solo lectura."""
    def pasa(sql):
        try:
            solo_lectura(sql); return True
        except SystemExit:
            return False
    casos = [('SELECT acepta', pasa('SELECT * FROM prod')), ('WITH acepta', pasa('WITH x AS (SELECT 1) SELECT * FROM x')),
             ('PRAGMA table_info acepta', pasa('PRAGMA table_info(prod)')), ('DELETE rechaza', not pasa('DELETE FROM prod')),
             ('INSERT rechaza', not pasa('INSERT INTO prod VALUES (1)')), ('dos sentencias rechaza', not pasa('SELECT 1; DROP TABLE prod')),
             ('UPDATE dentro de WITH rechaza', not pasa('WITH x AS (SELECT 1) UPDATE prod SET a=1')),
             ('punto y coma final acepta', pasa('SELECT 1;'))]
    mal = [n for n, ok in casos if not ok]
    for n, ok in casos:
        print(('PASA ' if ok else 'FALLA') + ' · ' + n)
    print(f'autotest pm_lectura: {len(casos) - len(mal)}/{len(casos)} ' + ('PASA' if not mal else 'FALLA'))
    sys.exit(1 if mal else 0)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['--autotest']:
        autotest()
    if not a:
        sys.exit(__doc__)
    sql = "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name" if a[0] == 'tablas' else a[0]
    for f in consulta(sql):
        print(json.dumps(f, ensure_ascii=False))
