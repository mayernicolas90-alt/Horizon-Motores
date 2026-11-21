"""G01 · guardia: este repositorio sube solo a la cuenta de Loki (mayernicolas90-alt) y los commits salen a su nombre.
Corre como pre-push y en ci. (21/11: el primer commit de controles salió firmado por la otra cuenta.)"""
import os, subprocess, sys
CUENTA = 'mayernicolas90-alt'


def correr(modo):
    if modo == 'ci':
        repo = os.environ.get('GITHUB_REPOSITORY', '')
        return ('PASA', repo) if not repo or repo.startswith(CUENTA + '/') else ('FALLA', f'el código de Loki está en {repo}')
    git = lambda *a: subprocess.run(['git', *a], capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    url, autor = git('remote', 'get-url', 'origin'), git('config', 'user.name')
    if f'github.com/{CUENTA}/' not in url:
        return 'FALLA', f'origin apunta a {url}: no es la cuenta de Loki'
    if autor != CUENTA:
        return 'FALLA', f'los commits salen a nombre de {autor}: en este repositorio tiene que ser {CUENTA} (git config user.name)'
    return 'PASA', f'{url} · autor {autor}'


if __name__ == '__main__':   # uso como pre-push
    est, det = correr('local')
    print(f'G01 {est}: {det}')
    sys.exit(0 if est == 'PASA' else 1)
