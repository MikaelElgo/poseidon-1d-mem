"""Run a verified Increment 9 checkout without depending on notebook kernel imports."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import shutil
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
BASELINE_ZIP_SHA256 = 'ad6ef2ece0937203baee582e9be67950a8b4ca78176bdd21ac7e187d1d63bd7c'
PERMITTED_CHANGES = {'README.md', 'pyproject.toml', 'p2mem/__init__.py'}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def check_ledger(name, allowed=()):
    seen = set()
    mismatches = []
    for line in (ROOT/name).read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        digest, relative = line.split('  ', 1)
        p = PurePosixPath(relative)
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in relative
                and ':' not in relative and relative not in seen, 'Invalid ledger path')
        require(len(digest)==64 and all(c in '0123456789abcdef' for c in digest), 'Invalid ledger checksum')
        seen.add(relative)
        path = ROOT/relative
        require(path.is_file() and not path.is_symlink(), f'Missing package file: {relative}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            mismatches.append(relative)
    require(seen, 'Empty ledger')
    require(set(mismatches).issubset(allowed), 'Checksum mismatch: '+', '.join(mismatches))
    return {'entries': len(seen), 'permitted_mismatches': sorted(mismatches)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('review','regenerate'), default='review')
    parser.add_argument('--private-input-root', type=Path)
    args = parser.parse_args(argv)
    require(args.mode == 'regenerate' or args.private_input_root is None,
            'Private inputs were supplied in review mode; select regenerate explicitly')
    require(args.mode == 'review' or args.private_input_root is not None,
            'Regenerate mode requires --private-input-root with las/ and deviation/ folders')
    current = check_ledger('INCREMENT_09_SHA256SUMS.txt')
    baseline = check_ledger('INCREMENT_08_0_1_SHA256SUMS.txt', PERMITTED_CHANGES)
    require(baseline['entries']==262, 'Baseline ledger inventory changed')
    sys.path.insert(0, str(ROOT))
    import p2mem
    require(Path(p2mem.__file__).resolve().parent==ROOT/'p2mem', 'Wrong p2mem import location')
    require(p2mem.__version__=='0.9.0', 'Wrong p2mem version')
    from p2mem.io.elastic_workflow import (ARTIFACTS, CONFIG_FILES, MANIFEST_NAME,
        run_elastic_workflow, publish_elastic_outputs, sha256, validate_elastic_outputs)
    original = ROOT/'outputs/09_dynamic_elasticity'
    manifest = validate_elastic_outputs(original)
    require(manifest['config_sha256']=={p:sha256(ROOT/p) for p in CONFIG_FILES}, 'Output/config provenance mismatch')
    output = original
    comparison = None
    if args.mode=='regenerate':
        raw=args.private_input_root.expanduser().resolve()
        run=run_elastic_workflow(ROOT,raw/'las',raw/'deviation')
        output=publish_elastic_outputs(run,ROOT/'outputs/09_dynamic_elasticity_regenerated')
        regenerated=validate_elastic_outputs(output)
        data_names=[n for n in ARTIFACTS if n.endswith('.csv')]
        require(all((output/n).read_bytes()==(original/n).read_bytes() for n in data_names),
                'Regenerated CSV results differ from the approved packaged results')
        # PNG bytes can depend on matplotlib; their hashes are therefore compared
        # separately from the scientific manifest content.
        old_science={k:v for k,v in manifest.items() if k!='artifacts'}
        new_science={k:v for k,v in regenerated.items() if k!='artifacts'}
        require(old_science==new_science, 'Regenerated scientific manifest differs')
        comparison={'csv_byte_identical':len(data_names), 'scientific_manifest_equal':True,
                    'png_byte_identical':sum((output/n).read_bytes()==(original/n).read_bytes()
                                             for n in ARTIFACTS if n.endswith('.png'))}
    record_dir=ROOT/'run_records'
    record_dir.mkdir(exist_ok=True)
    junit=record_dir/'increment_09_pytest.xml'
    junit.unlink(missing_ok=True)
    # Some locked integration tests intentionally regenerate older figures.
    # Execute those tests unchanged in a disposable copy of the verified files.
    # Their behavior must never mutate the release the notebook is reviewing.
    with tempfile.TemporaryDirectory(prefix='poseidon_inc09_tests_') as temporary:
        test_root=Path(temporary)
        relatives=[line.split('  ',1)[1] for line in
            (ROOT/'INCREMENT_09_SHA256SUMS.txt').read_text(encoding='utf-8').splitlines()
            if line and not line.startswith('#')]
        for relative in relatives+['INCREMENT_09_SHA256SUMS.txt']:
            target=test_root/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/relative,target)
        env=os.environ.copy()
        env['PYTHONPATH']=os.pathsep.join((str(test_root),str(test_root/'tests'),env.get('PYTHONPATH','')))
        env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
        proc=subprocess.run([sys.executable,'-m','pytest','-q','--import-mode=prepend',
                             '--junitxml',str(junit)],cwd=test_root,env=env,text=True,
                             stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
    (record_dir/'increment_09_pytest.log').write_text(proc.stdout,encoding='utf-8')
    print(proc.stdout)
    require(proc.returncode==0 and junit.is_file(), 'Test suite failed; see run_records/increment_09_pytest.log')
    suites=ET.parse(junit).getroot()
    cases=list(suites.iter('testcase'))
    require(cases and not list(suites.iter('failure')) and not list(suites.iter('error'))
            and not list(suites.iter('skipped')), 'Tests failed, errored or skipped')
    prior=[c for c in cases if c.attrib.get('classname','').split('.')[-1]
           not in ('test_dynamic_elasticity','test_elastic_workflow')]
    require(len(prior)==1632, 'Locked test subset count changed')
    check_ledger('INCREMENT_09_SHA256SUMS.txt')
    gate={'mode':args.mode,'package_version':p2mem.__version__,'baseline_zip_sha256':BASELINE_ZIP_SHA256,
          'package_ledger':current,'baseline_ledger':baseline,'tests_passed':len(cases),
          'locked_tests_passed':len(prior),'increment_09_tests_passed':len(cases)-len(prior),
          'tests_run_in_disposable_verified_copy':True,
          'serialized_outputs_validated':len(ARTIFACTS)+1,'regeneration_comparison':comparison,
          'declared_scope':'dynamic_elasticity_only','python':sys.version.split()[0]}
    (record_dir/'increment_09_run.json').write_text(json.dumps(gate,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(gate,indent=2))
    print('PASS: Increment 9 '+args.mode+' completed. Results: '+str(output))
    return gate


if __name__=='__main__':
    main()
