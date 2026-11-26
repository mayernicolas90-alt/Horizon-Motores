"""partir_respaldo.py 1.0 · plan B del arranque cuando no se puede leer el CRM 5SPm con ArtifactData.
Parte el respaldo del CRM 5SPm (Horizon-CRM-respaldo-AAAA-MM-DD.json) en RAIZ/CRM/<coleccion>/<id>.json
para que loki_sql.py abrir lo cargue como copia completa. Uso: python3 -I partir_respaldo.py RESPALDO.json RAIZ/CRM
Después: loki_sql.py abrir RAIZ HOY --crm RAIZ/CRM --origen 5SPm4UZTgiF5JXx7GKTybq --reglas (sin --incremental).
Solo oportunidades, cotizaciones y muestras (nunca config: D10). OJO: borra RAIZ/CRM antes de escribir.
1.0 (26/11, hacelo de Nicolás): venía de la skill loki de la nube (respaldo del 26/11), sin cambios de lógica."""
import json, os, shutil, sys

COLS = ('oportunidades', 'cotizaciones', 'muestras')


def main(src, out):
    d = json.load(open(src, encoding='utf-8'))
    if d.get('format') != 'horizon-crm' or 'collections' not in d:
        sys.exit('FALLA: no es un respaldo horizon-crm')
    faltan = [c for c in ('oportunidades', 'cotizaciones') if not d['collections'].get(c)]
    if faltan:
        sys.exit('FALLA: el respaldo no trae ' + ', '.join(faltan))
    if os.path.isdir(out):
        shutil.rmtree(out)
    n = {}
    for c in COLS:
        os.makedirs(os.path.join(out, c), exist_ok=True)
        docs = d['collections'].get(c) or {}
        for k, v in docs.items():
            if '/' in k or k.startswith('.'):
                sys.exit(f'FALLA: id inválido {c}/{k}')
            with open(os.path.join(out, c, k + '.json'), 'w', encoding='utf-8') as f:
                json.dump(v, f, ensure_ascii=False)
        n[c] = len(docs)
    print(f"OK respaldo {d.get('exportedAt', '?')} · " + ' · '.join(f'{c} {n[c]}' for c in COLS))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
