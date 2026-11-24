"""G02 · guardia de Claude Code (PreToolUse sobre ArtifactData): una escritura en el CRM necesita «hacelo» (o «armalo»)
en el último mensaje de Nicolás. Si no está, la acción se frena (código 2) y Claude recibe el motivo.
Excepción: la copia del CRM al abrir es solo lectura (get/list/query) y no pasa por acá.
Excepción DEC-1124c/f (24/11): el Publicador del datacenter puede escribir sin «hacelo» solo lo que preparó con el auditor en
PASA o AVISO: cada escritura tiene que coincidir con su manifiesto (colección, documento, archivo y huella) y el manifiesto
tiene que tener menos de 3 horas. Cualquier otra escritura sigue necesitando «hacelo»."""
import datetime as D, hashlib, json, os, sys, re

ESCRIBE = {'set', 'update', 'delete', 'str_replace', 'batch'}
OK = re.compile(r'\b(hacelo|hacelo\.|armalo)\b', re.I)


def ultimo_mensaje(transcript):
    ult = ''
    for linea in open(transcript, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(linea)
        except ValueError:
            continue
        if x.get('type') != 'user' or x.get('isMeta'):
            continue
        c = (x.get('message') or {}).get('content')
        if isinstance(c, str):
            ult = c
        elif isinstance(c, list):
            textos = [b.get('text', '') for b in c if isinstance(b, dict) and b.get('type') == 'text']
            if textos and not any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in c):
                ult = ' '.join(textos)
    return ult


MANIFIESTO = os.path.expanduser('~/.cache/loki-publicador/manifiesto.json')
VOLATIL = {'actualizado', 'generado'}


def huella_archivo(p):
    d = json.load(open(p, encoding='utf-8'))
    d = {k: v for k, v in d.items() if k not in VOLATIL}
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:16]


def del_publicador(ti, manifiesto=None):
    """True si todas las escrituras son del paquete vigente del Publicador."""
    try:
        man = json.load(open(manifiesto or MANIFIESTO, encoding='utf-8'))
        edad = D.datetime.now(D.timezone.utc) - D.datetime.strptime(man['creado'][:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=D.timezone.utc)
        if man.get('auditor') not in ('PASA', 'AVISO') or edad > D.timedelta(hours=3):
            return False
        ok = {(c['collection'], c['doc_id']): c for c in man['cambios']}
        writes = ti.get('writes') if ti.get('action') == 'batch' else [ti]
        if not writes:
            return False
        for w in writes:
            c = ok.get((w.get('collection'), w.get('doc_id')))
            if not c or w.get('op', ti.get('action')) not in ('set',) or w.get('data') is not None or w.get('file_path') != c['file_path'] \
                    or huella_archivo(w['file_path']) != c['sha']:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def decidir(evento, manifiesto=None):
    ti = evento.get('tool_input') or {}
    if ti.get('action') not in ESCRIBE:
        return 0, ''
    if del_publicador(ti, manifiesto):
        return 0, ''
    msg = ultimo_mensaje(evento['transcript_path']) if evento.get('transcript_path') else ''
    if OK.search(msg or ''):
        return 0, ''
    return 2, ('G02 · D01: escribir en el CRM necesita «hacelo» de Nicolás en su último mensaje. '
               'Proponé qué vas a cambiar y esperá el «hacelo».')


def correr(modo):
    """Autotest con transcripts inventados."""
    import tempfile, os
    def tr(texto):
        f = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False, encoding='utf-8')
        f.write(json.dumps({'type': 'user', 'message': {'content': texto}}) + '\n')
        f.write(json.dumps({'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': 'x'}]}}) + '\n'); f.close()
        return f.name
    d = tempfile.mkdtemp()
    doc = os.path.join(d, 'doc.json'); json.dump({'cuit': '1', 'lineas': [], 'actualizado': 'x'}, open(doc, 'w'))
    man = os.path.join(d, 'm.json')
    def manif(auditor='PASA', horas=0, sha=None):
        json.dump({'creado': (D.datetime.now(D.timezone.utc) - D.timedelta(hours=horas)).strftime('%Y-%m-%dT%H:%M:%S.000Z'), 'auditor': auditor,
                   'cambios': [{'collection': 'comprasLimpias', 'doc_id': '1', 'file_path': doc, 'sha': sha or huella_archivo(doc)}]}, open(man, 'w'))
    w = lambda **k: {'tool_input': dict({'action': 'batch', 'writes': [dict({'op': 'set', 'collection': 'comprasLimpias', 'doc_id': '1', 'file_path': doc}, **k)]}),
                     'transcript_path': tr('dale')}
    manif(); pub_ok = decidir(w(), man)[0] == 0
    otra = decidir(w(collection='oportunidades'), man)[0] == 2
    manif(sha='otra'); cambiado = decidir(w(), man)[0] == 2
    manif('FALLA'); falla = decidir(w(), man)[0] == 2
    manif(horas=4); viejo = decidir(w(), man)[0] == 2
    casos = [('escribir sin hacelo se frena', decidir({'tool_input': {'action': 'update'}, 'transcript_path': tr('fijate esto')})[0] == 2),
             ('Publicador: escritura del paquete vigente pasa sin hacelo', pub_ok),
             ('Publicador: otra colección o archivo cambiado o auditor FALLA o paquete viejo se frenan', otra and cambiado and falla and viejo),
             ('escribir con hacelo pasa', decidir({'tool_input': {'action': 'batch'}, 'transcript_path': tr('Hacelo')})[0] == 0),
             ('leer no se frena', decidir({'tool_input': {'action': 'query'}, 'transcript_path': tr('nada')})[0] == 0)]
    mal = [n for n, ok in casos if not ok]
    return ('FALLA', ', '.join(mal)) if mal else ('PASA', f'{len(casos)} casos')


if __name__ == '__main__':
    ev = json.load(sys.stdin)
    cod, msg = decidir(ev)
    if cod:
        print(msg, file=sys.stderr)
    sys.exit(cod)
