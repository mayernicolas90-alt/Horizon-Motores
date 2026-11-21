#!/usr/bin/env python3
"""Verifica que los scripts de Loki sean idénticos a los sellados (loki/huellas.json) y corre sus autotests.
Uso: python3 -I -X utf8 loki/verificar.py  → RESULTADO: PASA | FALLA (salida 0 / 1). Solo biblioteca estándar."""
import hashlib, json, os, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def h12(ruta):
    with open(ruta, encoding="utf-8", newline="") as fh:
        return hashlib.sha256(fh.read().replace("\r\n", "\n").encode()).hexdigest()[:12]


def main():
    cfg = json.load(open(os.path.join(AQUI, "huellas.json"), encoding="utf-8"))
    ok = True
    for nombre, m in sorted(cfg["scripts"].items()):
        p = os.path.join(AQUI, nombre)
        if not os.path.exists(p):
            print(f"FALLA · {nombre}: no está"); ok = False; continue
        h = h12(p)
        if h != m["huella"]:
            print(f"FALLA · {nombre}: huella {h} y la sellada es {m['huella']} (v{m['version']})"); ok = False; continue
        if not m.get("test"):
            print(f"PASA  · {nombre}: huella {h} (sin autotest)"); continue
        r = subprocess.run([sys.executable, "-X", "utf8", "-I", p] + m["test"], capture_output=True, text=True, encoding="utf-8", cwd=AQUI)
        fin = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()][-1:] or ["sin salida"]
        bien = r.returncode == 0
        print(f"{'PASA ' if bien else 'FALLA'} · {nombre}: huella {h} · {fin[0].strip()}")
        if not bien:
            print((r.stdout + r.stderr)[-1500:]); ok = False
    print(f"\nRESULTADO: {'PASA' if ok else 'FALLA'} · loki sellado {cfg['sellado']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
