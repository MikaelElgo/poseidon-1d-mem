import hashlib
import importlib.util
from pathlib import Path
import stat
import zipfile
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('inc10_bootstrap',ROOT/'scripts/bootstrap_increment_10.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


def make_zip(path,extras=(),bad_hash=False):
    payload=b'hello';digest='0'*64 if bad_hash else hashlib.sha256(payload).hexdigest()
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('data.txt',payload);z.writestr(b.LEDGER_NAME,digest+'  data.txt\n')
        for name,value in extras:z.writestr(name,value)


def test_fresh_extraction_preserves_existing(tmp_path):
    z=tmp_path/'good.zip';make_zip(z)
    a=b.extract_release(z,tmp_path);(a/'data.txt').write_text('stale')
    new=b.extract_release(z,tmp_path)
    assert a!=new and (a/'data.txt').read_text()=='stale'
    assert (new/'data.txt').read_text()=='hello'

@pytest.mark.parametrize('name',['../escape','/absolute','x/../evil','a\\b','C:evil','./alias','a//b','data.txt','unlisted'])
def test_unsafe_or_extra_entry_rejected(tmp_path,name):
    z=tmp_path/'bad.zip'
    with pytest.warns(UserWarning) if name=='data.txt' else __import__('contextlib').nullcontext():
        make_zip(z,[(name,'bad')])
    with pytest.raises(ValueError):b.extract_release(z,tmp_path)
    assert not list(tmp_path.glob('poseidon_inc10_*'))


def test_bad_hash_rejected_and_cleaned(tmp_path):
    z=tmp_path/'bad.zip';make_zip(z,bad_hash=True)
    with pytest.raises(ValueError):b.extract_release(z,tmp_path)
    assert not list(tmp_path.glob('poseidon_inc10_*'))


def test_symlink_zip_entry_rejected(tmp_path):
    z=tmp_path/'symlink.zip';make_zip(z)
    with zipfile.ZipFile(z,'a') as archive:
        info=zipfile.ZipInfo('link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        archive.writestr(info,'data.txt')
    with pytest.raises(ValueError):b.extract_release(z,tmp_path)


def test_symlink_ancestor_rejected(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();(outside/'x').write_text('value')
    root=tmp_path/'root';root.mkdir();(root/'linked').symlink_to(outside,target_is_directory=True)
    (root/b.LEDGER_NAME).write_text(hashlib.sha256(b'value').hexdigest()+'  linked/x\n')
    with pytest.raises(ValueError):b.verify_tree(root)


def test_notebook_bootstrap_parity_and_clean_cells():
    import json
    nb=json.loads((ROOT/'10_Static_Mechanics_and_Rock_Strength_Scenarios.ipynb').read_text())
    source=(ROOT/'scripts/bootstrap_increment_10.py').read_text()
    assert ''.join(nb['cells'][4]['source'])==source
    assert len({c['id'] for c in nb['cells']})==len(nb['cells'])
    for cell in nb['cells']:
        text=''.join(cell['source'])
        assert not any(ord(x)<32 and x not in '\n\r\t' for x in text)
        if cell['cell_type']=='code':
            assert cell['outputs']==[] and cell['execution_count'] is None
            compile(text,'notebook_cell','exec')
