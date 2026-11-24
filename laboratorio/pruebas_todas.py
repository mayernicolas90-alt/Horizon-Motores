#!/usr/bin/env python3
"""pruebas_todas.py 0.1 · corre todas las pruebas de las herramientas de Loki de este repo y da un tablero PASA/FALLA.

  · loki/verificar.py (huellas + autotests sellados) y controles/correr.py ci
  · --autotest de cada motor de loki/ y de laboratorio/ que lo tenga
No escribe en Turso ni en el CRM: las pruebas usan solo datos de prueba. Sale con 1 si algo falla.
Uso: python3 -I laboratorio/pruebas_todas.py [--json salida.json]
"""
import glob, json, os, re, subprocess, sys, time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def correr(nombre, cmd):
    t = time.time()
    try:
        p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, timeout=300)
        out, code = (p.stdout + p.stderr).strip(), p.returncode
    except subprocess.TimeoutExpired:
        out, code = 'TIEMPO AGOTADO', 124
    ult = [l for l in out.splitlines() if l.strip()]
    m = re.search(r'(\d+)\s*/\s*(\d+)', ult[-1] if ult else '')
    return dict(prueba=nombre, estado='PASA' if code == 0 else 'FALLA', detalle=(ult[-1] if ult else '')[:120],
                casos=f'{m.group(1)}/{m.group(2)}' if m else None, segundos=round(time.time() - t, 1))


def main(a):
    res = [correr('verificar (huellas + autotests sellados)', [sys.executable, '-I', '-X', 'utf8', 'loki/verificar.py']),
           correr('controles ci', [sys.executable, '-I', '-X', 'utf8', 'controles/correr.py', 'ci'])]
    for f in sorted(glob.glob(os.path.join(RAIZ, 'loki', '*.py')) + glob.glob(os.path.join(RAIZ, 'laboratorio', '*.py'))):
        if os.path.basename(f) == 'pruebas_todas.py' or '--autotest' not in open(f, encoding='utf-8').read():
            continue
        res.append(correr(os.path.relpath(f, RAIZ), [sys.executable, '-I', '-X', 'utf8', f, '--autotest']))
    for r in res:
        print(f"{r['estado']:5} {r['prueba']:44} {r['casos'] or '':>7}  {r['detalle'][:70]}")
    falla = [r for r in res if r['estado'] != 'PASA']
    print(f"\nRESUMEN {len(res) - len(falla)}/{len(res)} PASA" + (f" · FALLAN: {', '.join(r['prueba'] for r in falla)}" if falla else ''))
    if '--json' in a:
        json.dump(res, open(a[a.index('--json') + 1], 'w'), ensure_ascii=False, indent=1)
    return 1 if falla else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
