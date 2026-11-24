"""Guarda el token de solo lectura de Turso horizon-msyer (base del PM) en el Administrador de credenciales
de Windows, destino «Loki/Turso horizon-msyer». El token se escribe oculto (getpass), no se muestra ni se guarda
en ningún archivo ni historial. Uso: python -I guardar_token_pm.py"""
import ctypes, ctypes.wintypes as W, getpass, sys

TARGET = 'Loki/Turso horizon-msyer'


class CRED(ctypes.Structure):
    _fields_ = [('Flags', W.DWORD), ('Type', W.DWORD), ('TargetName', W.LPWSTR), ('Comment', W.LPWSTR),
                ('LastWritten', W.FILETIME), ('CredentialBlobSize', W.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_char)),
                ('Persist', W.DWORD), ('AttributeCount', W.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', W.LPWSTR), ('UserName', W.LPWSTR)]


adv = ctypes.WinDLL('advapi32', use_last_error=True)


def existe():
    p = ctypes.POINTER(CRED)()
    if not adv.CredReadW(TARGET, 1, 0, ctypes.byref(p)):
        return False
    adv.CredFree(p)
    return True


tok = getpass.getpass('Pegá el token de solo lectura de horizon-msyer y apretá Enter (no se ve): ').strip()
if len(tok) < 20:
    sys.exit('No se guardó: el token parece vacío o incompleto.')
b = tok.encode()
c = CRED(Type=1, TargetName=TARGET, Comment='Token Turso solo lectura · base del PM', CredentialBlobSize=len(b),
         CredentialBlob=ctypes.cast(ctypes.create_string_buffer(b, len(b)), ctypes.POINTER(ctypes.c_char)),
         Persist=2, UserName='loki')
if not adv.CredWriteW(ctypes.byref(c), 0):
    sys.exit(f'No se guardó (error {ctypes.get_last_error()}).')
del tok, b
print('Guardado en el Administrador de credenciales: ' + TARGET if existe() else 'FALLA: no quedó guardado')
