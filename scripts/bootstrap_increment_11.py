"""Standard-library-only safe extraction and file-ledger checks for Colab."""
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from zipfile import ZipFile

LEDGER_NAME='INCREMENT_11_SHA256SUMS.txt'


def verify_tree(root):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():raise ValueError('Project root must be a regular directory')
    seen=set();ledger=root/LEDGER_NAME
    if not ledger.is_file() or ledger.is_symlink():raise ValueError('Increment 11 ledger missing')
    for line in ledger.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):continue
        try:digest,name=line.split('  ',1)
        except ValueError as exc:raise ValueError('Malformed ledger') from exc
        p=PurePosixPath(name)
        if (p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or p.as_posix()!=name
            or name in seen or not name or name==LEDGER_NAME):raise ValueError('Unsafe ledger path')
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Malformed checksum')
        seen.add(name);target=root/name
        if any(root.joinpath(*p.parts[:i]).is_symlink() for i in range(1,len(p.parts)+1)):
            raise ValueError('Symlink in release path')
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
            raise ValueError('Missing or changed release file: '+name)
    if not seen:raise ValueError('Empty ledger')
    return seen


def extract_release(archive,parent=None):
    archive=Path(archive)
    if not archive.is_file():raise FileNotFoundError('Set ZIP_PATH to the exact Increment 11 ZIP')
    parent=Path(parent) if parent is not None else Path(tempfile.gettempdir())
    parent.mkdir(parents=True,exist_ok=True);staging=None
    try:
        with ZipFile(archive) as z:
            names=set();total=0
            for info in z.infolist():
                name=info.filename;p=PurePosixPath(name);total+=info.file_size
                if (p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or p.as_posix()!=name
                    or name in names or not name or info.is_dir() or stat.S_ISLNK(info.external_attr>>16)):
                    raise ValueError('Unsafe or duplicate ZIP entry: '+name)
                names.add(name)
            if LEDGER_NAME not in names:raise ValueError('Incomplete ZIP: release ledger missing; download the complete Increment 11 release')
            if total>300_000_000 or len(names)>10000:raise ValueError('Unexpected package size')
            staging=Path(tempfile.mkdtemp(prefix='poseidon_inc11_',dir=parent))
            z.extractall(staging)
        listed=verify_tree(staging)
        if names!=listed|{LEDGER_NAME}:raise ValueError('ZIP and ledger inventories differ')
        return staging
    except BaseException:
        if staging is not None:shutil.rmtree(staging,ignore_errors=True)
        raise
