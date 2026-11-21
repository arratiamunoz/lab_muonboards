#!/usr/bin/env python3
"""Stage patch and run disconnected native C integration tests on Linux.
Requires Python 3, Git, GCC-compatible cc and glibc. Does not launch JANUS.
Point to the exact CAEN 5.0.4/FERS 2.2.5 source tree, not your data directory.
"""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
HASHES={
 'src/JanusC.c':(
  'fa309409c8f45bb966728881911f24a97acebc1f37f0aa24ed6906941539f1bf',
  '1bc39b442ecc767af73a10e80e0c38541321c384669a6768c7dc9aabdf3870b4'),
 'src/outputfiles.c':(
  'dbe6e92985b7be462dd054fdab939b10f361417d2c5d70d9c769c6d8e80f4879',
  '19dc6447106dee5a79cc76dd2cff46022f1626efb258d56019aff5e0aac0f4ca'),
}
def hashbytes(v): return hashlib.sha256(v).hexdigest()
def staged(vendor,dst):
    for name,known in HASHES.items():
        b=(vendor/name).read_bytes()
        if hashbytes(b) not in known:
            raise SystemExit(f'exact vendor base SHA mismatch: {name} {hashbytes(b)}')
        (dst/name).parent.mkdir(exist_ok=True,parents=True)
        (dst/name).write_bytes(b.replace(b'\r\n',b'\n'))
    for h in (vendor/'src').glob('*.h'):
        shutil.copyfile(h,dst/'src'/h.name)
    shutil.copytree(vendor/'ferslib/include',dst/'ferslib/include')
def go(argv,path):
    subprocess.run([str(a) for a in argv],cwd=path,check=True,env=dict(os.environ,TZ='UTC'))
def compile_variant(base, result, test_stock=False):
    opts=['cc','-D_GNU_SOURCE','-DFERS_5202','-I','src','-I','ferslib/include','-I','.', '-ffunction-sections','-fdata-sections']
    go(opts+['-Dmain=unused_vendor_main','-c','src/JanusC.c','-o','janus.o'],base)
    go(opts+['-c','src/outputfiles.c','-o','output.o'],base)
    if test_stock: opts.append('-DSTOCK_TEST')
    go(opts+['-Wl,--gc-sections,--wrap=fopen,--wrap=vfprintf,--wrap=fsync,--wrap=time',HERE/'test_janus_file_finalization.c','janus.o','output.o','-o','test'],base)
    result.mkdir()
    go([base/'test',result],base)

def main():
    a=argparse.ArgumentParser(__doc__)
    a.add_argument('vendor_root',type=Path)
    a.add_argument('--stage-only',type=Path,help='Apply in a newly created directory (no test/build); input untouched.')
    args=a.parse_args()
    vendor=args.vendor_root.resolve(strict=True)
    if args.stage_only:
        dest=args.stage_only.resolve()
        dest.mkdir(exist_ok=False)
        staged(vendor,dest)
        go(['git','apply','--check',HERE/'janus-file-finalization.patch'],dest)
        go(['git','apply',HERE/'janus-file-finalization.patch'],dest)
        print(f'Patched source in {dest}; stock untouched.')
        return
    if not sys.platform.startswith('linux'):
        raise SystemExit('Exact-source C fixture requires Linux/glibc. On Windows, run test_windows_file_api.py separately.')
    with tempfile.TemporaryDirectory(prefix='janus-offline-') as work:
        w=Path(work)
        old=w/'stock'; patched=w/'patched'
        staged(vendor,old)
        staged(vendor,patched)
        go(['git','apply','--check',HERE/'janus-file-finalization.patch'],patched)
        go(['git','apply',HERE/'janus-file-finalization.patch'],patched)
        compile_variant(old,w/'stock-results',True)
        compile_variant(patched,w/'patched-results')
        for n in ['Run100_list.csv','Run100_ServiceInfo.txt']:
            a=(w/'stock-results/DataFiles'/n).read_bytes()
            b=(w/'patched-results/DataFiles'/n).read_bytes()
            assert a==b,f'stock replay byte mismatch for {n}'
            print('Byte-identical successful stock/patched',n,len(b),hashbytes(b))
        assert b'Elapsed time = 1800.000 s' in (w/'patched-results/DataFiles/Run100_Info.txt').read_bytes()
        assert len((w/'patched-results/DataFiles/Run100_list.csv').read_bytes().splitlines())==6184*64+11
if __name__=='__main__': main()

