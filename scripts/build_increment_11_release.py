"""Build a complete ZIP from the verified release ledger, including the ledger.

Deliberately refuses missing ledgers and runs the real notebook bootstrap on
its output before exposing the finished archive. No ledger self-hashing.
"""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import tempfile
import zipfile
from bootstrap_increment_11 import verify_tree,extract_release,LEDGER_NAME


def build_release(root,destination):
    root=Path(root);destination=Path(destination)
    entries=verify_tree(root)
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(suffix='.zip',dir=destination.parent);os.close(fd);temp=Path(tmp)
    try:
        with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=False) as z:
            for name in sorted(entries|{LEDGER_NAME}):
                info=zipfile.ZipInfo(name,date_time=(2026,9,8,0,0,0));info.create_system=0
                z.writestr(info,(root/name).read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
        with zipfile.ZipFile(temp) as z:
            if z.testzip() is not None:raise ValueError('CRC verification failed')
        with tempfile.TemporaryDirectory() as d:
            unpacked=extract_release(temp,d)
            assert verify_tree(unpacked)==entries
        os.replace(temp,destination)
    finally:temp.unlink(missing_ok=True)
    return {'file':destination.name,'entries':len(entries)+1,'size_bytes':destination.stat().st_size,
            'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination');a=p.parse_args()
    print(build_release(Path(__file__).resolve().parents[1],a.destination))
