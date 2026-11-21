"""Token de Turso de Loki en el Administrador de credenciales de Windows (cifrado por usuario).
leer() lo devuelve; `python credencial.py guardar` lo toma de LOKI_TURSO_TOKEN y lo guarda."""
import ctypes, ctypes.wintypes as W, os, sys
TARGET = 'Loki/Turso horizon-nicom90'
class CRED(ctypes.Structure):
    _fields_ = [('Flags', W.DWORD), ('Type', W.DWORD), ('TargetName', W.LPWSTR), ('Comment', W.LPWSTR),
                ('LastWritten', W.FILETIME), ('CredentialBlobSize', W.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_char)),
                ('Persist', W.DWORD), ('AttributeCount', W.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', W.LPWSTR), ('UserName', W.LPWSTR)]
adv = ctypes.WinDLL('advapi32', use_last_error=True)
def guardar(tok):
    b = tok.encode()
    c = CRED(Type=1, TargetName=TARGET, Comment='Token Turso de Loki (base SQL)', CredentialBlobSize=len(b),
             CredentialBlob=ctypes.cast(ctypes.create_string_buffer(b, len(b)), ctypes.POINTER(ctypes.c_char)),
             Persist=2, UserName='loki')
    if not adv.CredWriteW(ctypes.byref(c), 0):
        raise OSError(ctypes.get_last_error())
def leer():
    p = ctypes.POINTER(CRED)()
    if not adv.CredReadW(TARGET, 1, 0, ctypes.byref(p)):
        return None
    try:
        return ctypes.string_at(p.contents.CredentialBlob, p.contents.CredentialBlobSize).decode()
    finally:
        adv.CredFree(p)
if __name__ == '__main__':
    if sys.argv[1:] == ['guardar']:
        guardar(os.environ['LOKI_TURSO_TOKEN']); print('guardado' if leer() else 'FALLA')
    else:
        print('hay token' if leer() else 'sin token')
