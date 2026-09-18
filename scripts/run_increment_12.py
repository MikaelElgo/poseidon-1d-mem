"""Review/reproduce WBS and run version-scoped historical and current tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from bootstrap_increment_12 import verify_tree, LEDGER_NAME
from verify_increment_12_independent import verify
from compare_increment_12_reproduction import compare

ROOT=Path(__file__).resolve().parents[1]
NEW_TESTS=('test_wellbore_stability.py','test_wbs_workflow.py','test_increment12_release.py')
METADATA={'README.md','pyproject.toml','p2mem/__init__.py'}


def restore_baseline(root,dst):
    root=Path(root);dst=Path(dst)
    ledger=root/'INCREMENT_11_SHA256SUMS.txt'
    for line in ledger.read_text().splitlines():
        digest,rel=line.split('  ',1)
        source=root/'verification/increment_11_metadata'/rel if rel in METADATA else root/rel
        if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise ValueError('Increment 11 baseline altered: '+rel)
        target=dst/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    shutil.copyfile(ledger,dst/ledger.name)


def run_tests(dst,records,label,tests=()):
    env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join((str(dst),str(dst/'tests')));env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    junit=dst/'test_results.xml'
    result=subprocess.run([sys.executable,'-m','pytest','-q','--import-mode=prepend','--junitxml',str(junit),*tests],cwd=dst,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    print(result.stdout);(records/(label+'.log')).write_text(result.stdout)
    if result.returncode:raise RuntimeError(label+' failed')
    tree=ET.parse(junit).getroot();cases=list(tree.iter('testcase'))
    if any(list(tree.iter(k)) for k in ('failure','error','skipped')):raise RuntimeError('JUnit failure/error/skip')
    shutil.copyfile(junit,records/(label+'.xml'));return len(cases)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--mode',choices=('review','reproduce'),default='review');args=parser.parse_args(argv)
    entries=verify_tree(ROOT);sys.path.insert(0,str(ROOT))
    import p2mem
    from p2mem.io.wbs_workflow import validate,publish,DESTINATION
    assert p2mem.__version__=='0.12.0' and Path(p2mem.__file__).resolve().parent==ROOT/'p2mem'
    manifest=validate(ROOT);independent=verify(ROOT/DESTINATION);comparison=None
    if args.mode=='reproduce':
        destination=ROOT/'outputs/12_wellbore_stability_regenerated';publish(ROOT,destination);validate(ROOT,destination)
        comparison=compare(ROOT/DESTINATION,destination)
        # Validate regenerated science independently as well as its own hashes.
        comparison['regenerated_independent']=verify(destination)
    records=ROOT/'run_records';records.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='inc12_historical_') as d:
        dst=Path(d);restore_baseline(ROOT,dst)
        historical=run_tests(dst,records,'increment_12_historical')
        if historical!=1929:raise RuntimeError('Historical test inventory changed')
    with tempfile.TemporaryDirectory(prefix='inc12_current_') as d:
        dst=Path(d)
        for rel in entries|{LEDGER_NAME}:
            target=dst/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,target)
        new=run_tests(dst,records,'increment_12_current',[str(Path('tests')/x) for x in NEW_TESTS])
    verify_tree(ROOT)
    report={'mode':args.mode,'package_version':p2mem.__version__,'python':sys.version.split()[0],
            'tests_passed':historical+new,'historical_baseline_tests':historical,'current_increment_tests':new,
            'test_scope':'historical suite on checksum-restored exact Increment 11; new tests on current Increment 12',
            'ledger_files':len(entries),'independent':independent,'comparison':comparison,'coverage':manifest['coverage'],
            'hosted_colab_execution_claim':False,'raw_regeneration_claim':False}
    (records/'increment_12_run.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return report

if __name__=='__main__':main()
