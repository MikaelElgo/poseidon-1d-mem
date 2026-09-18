"""Review/reproduce Increment 10 and run all tests in an isolated release copy."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
LEDGER='INCREMENT_10_SHA256SUMS.txt'
BASELINE='INCREMENT_09_SHA256SUMS.txt'
ALLOWED_CHANGES={'README.md','pyproject.toml','p2mem/__init__.py'}


def require(ok,message):
    if not ok:raise RuntimeError(message)


def check_ledger(root,name,allowed=()):
    root=Path(root);seen={};bad=[]
    for line in (root/name).read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):continue
        digest,relative=line.split('  ',1);p=PurePosixPath(relative)
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in relative and ':' not in relative
                and p.as_posix()==relative and relative not in seen,'Unsafe ledger path')
        require(len(digest)==64 and all(x in '0123456789abcdef' for x in digest),'Malformed digest')
        target=root/relative
        require(target.is_file() and not target.is_symlink(),'Missing/nonregular file: '+relative)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:bad.append(relative)
        seen[relative]=digest
    require(seen,'Empty ledger');require(set(bad).issubset(allowed),'Checksum mismatch: '+', '.join(bad))
    return seen,bad


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('review','reproduce'),default='review')
    args=parser.parse_args(argv)
    entries,_=check_ledger(ROOT,LEDGER);baseline,bad=check_ledger(ROOT,BASELINE,ALLOWED_CHANGES)
    require(len(baseline)==282,'Unexpected baseline inventory')
    sys.path.insert(0,str(ROOT))
    import p2mem
    require(p2mem.__version__=='0.10.0' and Path(p2mem.__file__).resolve().parent==ROOT/'p2mem','Wrong package import')
    from p2mem.io.mechanics_workflow import DESTINATION,DATA_FILES,FIGURES,build,publish,validate,expected_tables,compare_table
    from verify_increment_10_independent import verify
    run=build(ROOT);output=ROOT/DESTINATION;manifest=validate(ROOT,output,run=run)
    comparison=None
    if args.mode=='reproduce':
        destination=ROOT/(DESTINATION+'_regenerated');publish(ROOT,destination)
        reproduced=validate(ROOT,destination,run=run)
        for name,(fields,rows) in expected_tables(run).items():compare_table(destination/name,fields,rows)
        comparison={'scientific_tables_equal_within_tolerance':len(DATA_FILES),
            'tables_byte_identical':sum((output/name).read_bytes()==(destination/name).read_bytes() for name in DATA_FILES),
            'figures_byte_identical':sum((output/name).read_bytes()==(destination/name).read_bytes() for name in FIGURES),
            'source':'packaged Increment 9 derived outputs; not raw-source regeneration'}
        output=destination
    independent=verify(output)
    records=ROOT/'run_records';records.mkdir(exist_ok=True);junit=records/'increment_10_pytest.xml';junit.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix='poseidon_inc10_tests_') as tmp:
        testroot=Path(tmp)
        for relative in list(entries)+[LEDGER]:
            target=testroot/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
        env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join((str(testroot),str(testroot/'tests')))
        env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
        process=subprocess.run([sys.executable,'-m','pytest','-q','--import-mode=prepend','--junitxml',str(junit)],
            cwd=testroot,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
    (records/'increment_10_pytest.log').write_text(process.stdout,encoding='utf-8');print(process.stdout)
    require(process.returncode==0 and junit.exists(),'Test suite failed; inspect run_records/increment_10_pytest.log')
    suite=ET.parse(junit).getroot();cases=list(suite.iter('testcase'))
    require(cases and not any(list(suite.iter(x)) for x in ('failure','error','skipped')),'Test failure/error/skip')
    old=[t for t in cases if t.attrib.get('classname','').split('.')[-1] not in ('test_mechanics','test_mechanics_workflow','test_increment10_bootstrap')]
    require(len(old)==1754,'Historical test inventory changed')
    check_ledger(ROOT,LEDGER)
    report={'mode':args.mode,'package_version':p2mem.__version__,'python':sys.version.split()[0],
        'tests_passed':len(cases),'historical_tests_passed':len(old),'increment_10_tests_passed':len(cases)-len(old),
        'ledger_files_verified':len(entries),'baseline_metadata_changes':bad,'independent_checks':independent,
        'coverage':manifest['coverage'],'comparison':comparison,'output_directory':output.name,
        'no_raw_regeneration_claim':True,'no_hosted_colab_claim':True,'field_mechanics_eligible_count':0}
    (records/'increment_10_run.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2));print('PASS: Increment 10 '+args.mode+' complete. Field mechanics remain withheld.')
    return report

if __name__=='__main__':main()
