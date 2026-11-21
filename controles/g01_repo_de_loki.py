"""G01 · guardia: este repositorio sube solo a la cuenta de Loki (mayernicolas90-alt). Corre como pre-push y en ci."""
import os, subprocess, sys
CUENTA = 'mayernicolas90-alt'


def correr(modo):
    if modo == 'ci':
        repo = os.environ.get('GITHUB_REPOSITORY', '')
        return ('PASA', repo) if not repo or repo.startswith(CUENTA + '/') else ('FALLA', f'el código de Loki está en {repo}')
    url = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    return ('PASA', url) if f'github.com/{CUENTA}/' in url else ('FALLA', f'origin apunta a {url}: no es la cuenta de Loki')


if __name__ == '__main__':   # uso como pre-push
    est, det = correr('local')
    print(f'G01 {est}: {det}')
    sys.exit(0 if est == 'PASA' else 1)
