from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import zipfile
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_increment_12 import LEDGER_NAME,extract_release,verify_tree
from build_increment_12_release import build_release


def test_real_final_archive_roundtrip(tmp_path):
    # Regression for delivered Increment 10 archives omitting their ledger.
    out=tmp_path/'complete.zip';result=build_release(ROOT,out)
    with zipfile.ZipFile(out) as z:assert LEDGER_NAME in z.namelist()
    dst=extract_release(out,tmp_path)
    assert result['entries']==len(verify_tree(dst))+1
    assert (dst/'12_Wellbore_Stability_Envelopes.ipynb').is_file()


def test_missing_ledger_zip_rejected_before_extraction(tmp_path):
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('README.md','no ledger')
    with pytest.raises(ValueError,match='ledger missing'):extract_release(p,tmp_path)
    assert not list(tmp_path.glob('poseidon_inc12_*'))

@pytest.mark.parametrize('name',['../escape','/absolute','a\\b','C:evil','a//b'])
def test_unsafe_paths_rejected(tmp_path,name):
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(p,'w') as z:
        z.writestr(LEDGER_NAME,hashlib.sha256(b'hi').hexdigest()+'  '+name+'\n');z.writestr(name,'hi')
    with pytest.raises(ValueError):extract_release(p,tmp_path)


def test_notebook_parity_and_syntax():
    nb=json.loads((ROOT/'12_Wellbore_Stability_Envelopes.ipynb').read_text())
    codes=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code']
    assert (ROOT/'scripts/bootstrap_increment_12.py').read_text() in codes
    assert len({c['id'] for c in nb['cells']})==len(nb['cells'])
    for c in nb['cells']:
        if c['cell_type']=='code':
            assert c['outputs']==[] and c['execution_count'] is None
            compile(''.join(c['source']),'cell','exec')


def test_corrupt_payload_and_extra_file_rejected(tmp_path):
    for extra in (False,True):
        p=tmp_path/('extra.zip' if extra else 'changed.zip')
        with zipfile.ZipFile(p,'w') as z:
            z.writestr(LEDGER_NAME,hashlib.sha256(b'original').hexdigest()+'  '+'payload.txt\n')
            z.writestr('payload.txt',b'original' if extra else b'changed')
            if extra:z.writestr('unlisted.txt','extra')
        with pytest.raises(ValueError):extract_release(p,tmp_path)


def test_truncated_archive_rejected(tmp_path):
    p=tmp_path/'truncated.zip';p.write_bytes(b'PK\x03\x04'+b'\0'*20)
    with pytest.raises(zipfile.BadZipFile):extract_release(p,tmp_path)
