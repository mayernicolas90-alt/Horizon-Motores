"""C06 · El arranque lee el conocimiento en tablas (k_*), no la prosa del cerebro (tema #1002).
ci: corre el autotest de loki_sql.py y exige las 5 pruebas de conocimiento.
diario: la base tiene reglas duras vigentes en k_regla y el loki_sql.py de la tabla scripts trae conocimiento()."""
import os, subprocess, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRUEBAS = ('sin k_regla: conocimiento None', 'conocimiento: dura entera', 'conocimiento: preferencias',
           'regla desde k_regla', 'reglas --tipo dura desde k_regla')


def correr(modo):
    if modo == 'ci':
        p = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(RAIZ, 'loki', 'loki_sql.py'), '--autotest'],
                           capture_output=True, text=True, encoding='utf-8')
        bien = [l for l in p.stdout.splitlines() if l.startswith('BIEN')]
        faltan = [t for t in PRUEBAS if not any(t in l for l in bien)]
        if faltan:
            return 'FALLA', 'el arranque no prueba la lectura de k_*: ' + ' | '.join(faltan)
        return 'PASA', '5/5 pruebas de conocimiento en el autotest'
    sys.path.insert(0, os.path.join(RAIZ, 'loki'))
    from bitacora2 import turso
    n = int(turso("SELECT COUNT(*) n FROM k_regla WHERE estado='vigente' AND dura=1")[0]['n'])
    s = turso("SELECT texto FROM scripts WHERE nombre='loki_sql.py'")
    if not n:
        return 'FALLA', 'k_regla sin reglas duras vigentes: el arranque no tiene qué leer'
    if not s or 'def conocimiento(' not in s[0]['texto']:
        return 'FALLA', 'el loki_sql.py de la base todavía lee la prosa del cerebro'
    return 'PASA', f'{n} reglas duras vigentes en k_regla; el arranque las lee'
