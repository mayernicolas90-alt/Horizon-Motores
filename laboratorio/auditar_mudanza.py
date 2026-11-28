"""Auditoría de la mudanza Turso (horizon-nicom90) → Supabase, fila por fila. Solo lectura en las dos bases.
Compara las columnas del origen (las de Supabase que no están en Turso, como dueno, mudado o cuit11, se ignoran).
Normaliza: números como float (tolerancia 1e-6), JSON en texto parseado y comparado canónico, '' y NULL distintos.
Uso: python3 -I auditar_mudanza.py SALIDA_DIR"""
import json, math, os, subprocess, sys, collections

R = os.environ.get('LOKI_SCRATCH', os.path.dirname(os.path.abspath(__file__)))
LOKI = [sys.executable, '-I', R + '/loki/BIN/loki_sql.py', 'sql']
SBQ = R + '/sbq.sh'
PARES = [('clientes', 'cuenta', 'cue_cuentas'), ('clientes', 'cuit', 'cue_cuit'), ('clientes', 'marca', 'cue_marca'),
         ('clientes', 'alias', 'cliente_alias'),
         ('comercial', 'oportunidad', 'crm_oportunidad'), ('comercial', 'contacto', 'crm_contacto'),
         ('comercial', 'historial', 'crm_historial'), ('comercial', 'cotizacion', 'crm_cotizacion'),
         ('comercial', 'cotizacion_item', 'crm_cotizacion_item'), ('comercial', 'muestra', 'crm_muestra'),
         ('motores', 'recompra_cliente', 'rec_cliente'), ('motores', 'recompra_sku', 'rec_sku'),
         ('motores', 'puntaje', 'pun_fichas'), ('motores', 'status', 'status_cliente'), ('motores', 'portada', 'por_dia'),
         ('operacion', 'bitacora', 'bitacora'), ('operacion', 'tema', 'tema'), ('operacion', 'tema_evento', 'tema_evento'),
         ('operacion', 'continuidad', 'continuidad'), ('conocimiento', 'regla', 'k_regla'), ('conocimiento', 'decision', 'k_decision'),
         ('conocimiento', 'preferencia', 'k_preferencia'), ('conocimiento', 'procedimiento', 'k_procedimiento'),
         ('conocimiento', 'motor', 'k_motor'), ('conocimiento', 'fuente', 'k_fuente'), ('conocimiento', 'documento', 'k_documento')]


def turso(sql):
    out = subprocess.run(LOKI + [sql], capture_output=True, text=True, check=True).stdout
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def supa(sql):
    import time
    for i in range(6):   # la API de administración limita pedidos por minuto (429): espera y reintenta
        out = subprocess.run([SBQ, sql], capture_output=True, text=True, check=True).stdout.rsplit('\n', 2)
        if out[-2].strip() != '429':
            break
        time.sleep(10 * (i + 1))
    if out[-2].strip() not in ('200', '201'):
        raise RuntimeError(f'Supabase {out[-2]}: {out[0][:300]}')
    return json.loads(out[0])


def norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return ('n', round(float(v), 6))
    if isinstance(v, (dict, list)):
        return ('j', json.dumps(v, sort_keys=True, ensure_ascii=False))
    s = str(v)
    try:
        f = float(s)
        if math.isfinite(f) and s.strip() == s and s not in ('',):
            return ('n', round(f, 6))
    except ValueError:
        pass
    if s[:1] in '[{':
        try:
            return ('j', json.dumps(json.loads(s), sort_keys=True, ensure_ascii=False))
        except ValueError:
            pass
    return ('s', s)


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    res = []
    for esq, tab, origen in PARES:
        cols_t = [r['name'] for r in turso(f'PRAGMA table_info({origen})')]
        cols_s = [r['column_name'] for r in supa(
            f"SELECT column_name FROM information_schema.columns WHERE table_schema='{esq}' AND table_name='{tab}' ORDER BY ordinal_position")]
        comunes = [c for c in cols_t if c in cols_s]
        faltan = [c for c in cols_t if c not in cols_s]
        sel = ', '.join(f'"{c}"' for c in comunes)
        a = turso(f'SELECT {sel} FROM "{origen}"')
        b = supa(f'SELECT {sel} FROM {esq}."{tab}"')
        ka = collections.Counter(tuple(json.dumps(norm(r.get(c)), ensure_ascii=False) for c in comunes) for r in a)
        kb = collections.Counter(tuple(json.dumps(norm(r.get(c)), ensure_ascii=False) for c in comunes) for r in b)
        solo_a, solo_b = ka - kb, kb - ka
        iguales = sum((ka & kb).values())
        ok = not solo_a and not solo_b and not faltan and len(a) == len(b)
        ej = []
        for k in list(solo_a)[:3]:
            ej.append({'solo_turso': dict(zip(comunes, (json.loads(x) for x in k)))})
        for k in list(solo_b)[:3]:
            ej.append({'solo_supabase': dict(zip(comunes, (json.loads(x) for x in k)))})
        r = dict(tabla=f'{esq}.{tab}', origen=origen, turso=len(a), supabase=len(b), iguales=iguales,
                 solo_turso=sum(solo_a.values()), solo_supabase=sum(solo_b.values()), columnas=len(comunes),
                 columnas_faltantes=faltan, extra_supabase=[c for c in cols_s if c not in cols_t],
                 resultado='PASA' if ok else 'FALLA')
        res.append(r)
        json.dump(ej, open(f'{out_dir}/{esq}.{tab}.diferencias.json', 'w'), ensure_ascii=False, indent=1, default=str)
        print(f"{r['resultado']:5s} {r['tabla']:28s} turso {r['turso']:5d} · supabase {r['supabase']:5d} · iguales {iguales:5d}"
              f" · solo turso {r['solo_turso']} · solo supabase {r['solo_supabase']} · columnas {len(comunes)}"
              + (f' · FALTAN {faltan}' if faltan else ''))
    json.dump(res, open(f'{out_dir}/resumen.json', 'w'), ensure_ascii=False, indent=1)
    return 0 if all(r['resultado'] == 'PASA' for r in res) else 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
