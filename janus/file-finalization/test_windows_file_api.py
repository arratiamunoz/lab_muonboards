"""Exercise Windows filesystem/UCRT assumptions only. No JANUS/FERS or hardware."""
from pathlib import Path
import ctypes as c
from ctypes import wintypes as w
import errno, os, tempfile

if os.name != 'nt':
    raise SystemExit('This optional test requires Windows.')
api=c.WinDLL('kernel32',use_last_error=True)
crt=c.CDLL('ucrtbase',use_errno=True)
crt.fopen.argtypes=[c.c_char_p,c.c_char_p];crt.fopen.restype=c.c_void_p
crt.fputs.argtypes=[c.c_char_p,c.c_void_p];crt.fputs.restype=c.c_int
for n in ('fflush','fclose','_fileno'):
    f=getattr(crt,n);f.argtypes=[c.c_void_p];f.restype=c.c_int
crt._commit.argtypes=[c.c_int];crt._commit.restype=c.c_int
api.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE]
api.CreateFileW.restype=w.HANDLE
api.ReadFile.argtypes=[w.HANDLE,w.LPVOID,w.DWORD,c.POINTER(w.DWORD),w.LPVOID];api.ReadFile.restype=w.BOOL
api.CloseHandle.argtypes=[w.HANDLE];api.CloseHandle.restype=w.BOOL
api.MoveFileExA.argtypes=[w.LPCSTR,w.LPCSTR,w.DWORD];api.MoveFileExA.restype=w.BOOL
INVALID=c.c_void_p(-1).value
SHARE_READ_WRITE=3
WRITE_THROUGH=8
def start(name):
    f=crt.fopen(name,b'wx')
    assert f,(name,c.get_errno())
    return f
def end(f):
    assert crt.fflush(f)==0
    assert crt._commit(crt._fileno(f))==0
    assert crt.fclose(f)==0
def metadata(stem):
    f=start(stem+b'.partial')
    assert crt.fputs(b'checked native info\n',f)>=0
    end(f)
    return bool(api.MoveFileExA(stem+b'.partial',stem,WRITE_THROUGH))

cwd=Path.cwd()
with tempfile.TemporaryDirectory(prefix='file-api-test-',dir=cwd) as d:
    assert Path(d).resolve().parent == cwd.resolve()
    os.chdir(d)
    try:
        f=start(b'Run100_list.csv')
        assert crt.fputs(b'trigger,channel\n0,0\n',f)>=0
        r=api.CreateFileW('Run100_list.csv',0x80000000,SHARE_READ_WRITE,None,3,0x80,None)
        assert r not in (None,INVALID), c.get_last_error()
        try:
            end(f)  # Reader does not grant FILE_SHARE_DELETE and remains open.
            assert metadata(b'Run100_Info.txt'),c.get_last_error()
            out=c.create_string_buffer(256); n=w.DWORD()
            assert api.ReadFile(r,out,len(out),c.byref(n),None)
            assert b'0,0' in out.raw[:n.value]
            assert Path('Run100_list.csv').exists()
        finally:
            assert api.CloseHandle(r)
        f=crt.fopen(b'Run100_list.csv',b'wx')
        if f: crt.fclose(f);raise AssertionError('exclusive fopen replaced existing file')
        assert c.get_errno() in (errno.EEXIST,errno.EACCES),c.get_errno()
        assert '0,0' in Path('Run100_list.csv').read_text()
        assert not metadata(b'Run100_Info.txt')
        assert c.get_last_error() in (80,183),c.get_last_error()
        assert Path('Run100_Info.txt').read_bytes()==Path('Run100_Info.txt.partial').read_bytes()
    finally:
        os.chdir(cwd)
print('PASS: actual Windows UCRT exclusive open/flush/_commit/close and Win32 no-replace RunInfo publish with preview reader open')

