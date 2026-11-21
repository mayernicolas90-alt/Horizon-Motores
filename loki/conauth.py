"""Lanzador de Loki (PC o nube): agrega el token de Turso a los pedidos
a turso.io y corre los subprocesos de Python en UTF-8. Uso: python -I -X utf8 conauth.py SCRIPT args...
Token: variable LOKI_TURSO_TOKEN (nube: secreto del entorno) o, en Windows, el Administrador de credenciales."""
import os, sys, runpy, subprocess, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_tok = os.environ.get('LOKI_TURSO_TOKEN')
if not _tok and os.name == 'nt':
    import credencial   # solo Windows
    _tok = credencial.leer()
if not _tok:
    sys.exit('FALLA sin token de Turso: variable LOKI_TURSO_TOKEN (nube) o Administrador de credenciales (PC)')
_orig = urllib.request.urlopen
def _open(rq, *a, **k):
    if isinstance(rq, urllib.request.Request) and 'turso.io' in rq.full_url and not rq.has_header('Authorization'):
        rq.add_header('Authorization', 'Bearer ' + _tok)
    return _orig(rq, *a, **k)
urllib.request.urlopen = _open
_run = subprocess.run
def _r(cmd, *a, **k):
    if isinstance(cmd, list) and cmd and cmd[0] == sys.executable and '-X' not in cmd:
        cmd = [cmd[0], '-X', 'utf8'] + cmd[1:]
    return _run(cmd, *a, **k)
subprocess.run = _r
script = sys.argv[1]; sys.argv = sys.argv[1:]
runpy.run_path(script, run_name='__main__')
