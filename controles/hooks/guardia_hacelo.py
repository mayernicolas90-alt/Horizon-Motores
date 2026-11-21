"""G02 · guardia de Claude Code (PreToolUse sobre ArtifactData): una escritura en el CRM necesita «hacelo» (o «armalo»)
en el último mensaje de Nicolás. Si no está, la acción se frena (código 2) y Claude recibe el motivo.
Excepción: la copia del CRM al abrir es solo lectura (get/list/query) y no pasa por acá."""
import json, sys, re

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


def decidir(evento):
    ti = evento.get('tool_input') or {}
    if ti.get('action') not in ESCRIBE:
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
    casos = [('escribir sin hacelo se frena', decidir({'tool_input': {'action': 'update'}, 'transcript_path': tr('fijate esto')})[0] == 2),
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
