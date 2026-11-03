import ctypes
import ctypes.wintypes as wt

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
TARGET = "DreamLandClient:%s"


class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wt.DWORD),
        ("Type", wt.DWORD),
        ("TargetName", wt.LPWSTR),
        ("Comment", wt.LPWSTR),
        ("LastWritten", wt.FILETIME),
        ("CredentialBlobSize", wt.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wt.DWORD),
        ("AttributeCount", wt.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wt.LPWSTR),
        ("UserName", wt.LPWSTR),
    ]


try:
    _adv = ctypes.WinDLL("advapi32", use_last_error=True)
    _adv.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wt.DWORD]
    _adv.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    _adv.CredDeleteW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD]
    _adv.CredFree.argtypes = [ctypes.c_void_p]
except (AttributeError, OSError):
    _adv = None


def save(name, password):
    if not _adv:
        return False
    blob = password.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = CREDENTIAL()
    c.Type = CRED_TYPE_GENERIC
    c.TargetName = TARGET % name.lower()
    c.CredentialBlobSize = len(blob)
    c.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    c.Persist = CRED_PERSIST_LOCAL_MACHINE
    c.UserName = name
    return bool(_adv.CredWriteW(ctypes.byref(c), 0))


def load(name):
    if not _adv or not name:
        return None
    p = ctypes.POINTER(CREDENTIAL)()
    if not _adv.CredReadW(TARGET % name.lower(), CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
        return None
    try:
        c = p.contents
        raw = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        _adv.CredFree(p)


def delete(name):
    if _adv and name:
        _adv.CredDeleteW(TARGET % name.lower(), CRED_TYPE_GENERIC, 0)
