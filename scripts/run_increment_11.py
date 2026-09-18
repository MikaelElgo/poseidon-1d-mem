"""Review or reproduce Increment 11; test in an isolated ledger-only copy."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from bootstrap_increment_11 import verify_tree,LEDGER_NAME
from verify_increment_11_independent import verify

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('review','reproduce'),default='review')
    args=parser.parse_args(argv)
    entries=verify_tree(ROOT)
    sys.path.insert(0,str(ROOT))
    from p2mem.io.stress_workflow import validate,publish,DESTINATION
    import p2mem
    assert p2mem.__version__=='0.11.0' and Path(p2mem.__file__).resolve().parent==ROOT/'p2mem'
    manifest=validate(ROOT)
    independent=verify(ROOT/DESTINATION)
    comparison=None
    if args.mode=='reproduce':
        temp=ROOT/'outputs/11_horizontal_stress_regenerated'
        publish(ROOT,temp);validate(ROOT,temp)
        a=ROOT/DESTINATION
        comparison={'tables_byte_identical':sum((a/k).read_bytes()==(temp/k).read_bytes() for k in manifest['row_counts']),
            'tables_compared':len(manifest['row_counts']),
            'figures_byte_identical':sum((a/k).read_bytes()==(temp/k).read_bytes() for k in manifest['figures']),
            'scope':'packaged derived upstream outputs; not raw regeneration'}
        assert comparison['tables_byte_identical']==comparison['tables_compared']
    records=ROOT/'run_records';records.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='inc11_suite_') as d:
        dst=Path(d)
        for rel in entries|{LEDGER_NAME}:
            target=dst/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,target)
        env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join((str(dst),str(dst/'tests')));env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
        junit=dst/'test_results.xml'
        p=subprocess.run([sys.executable,'-m','pytest','-q','--import-mode=prepend','--junitxml',str(junit)],cwd=dst,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        print(p.stdout);(records/'increment_11_pytest.log').write_text(p.stdout)
        if p.returncode!=0:raise RuntimeError('Cumulative tests failed; see run_records/increment_11_pytest.log')
        tree=ET.parse(junit).getroot();cases=list(tree.iter('testcase'))
        if any(list(tree.iter(k)) for k in ('failure','error','skipped')):raise RuntimeError('JUnit failure/error/skip')
        new=[c for c in cases if c.attrib.get('classname','').split('.')[-1] in ('test_horizontal_stress','test_stress_workflow','test_increment11_release')]
        if len(cases)-len(new)!=1852:raise RuntimeError('Historical test inventory changed')
        shutil.copyfile(junit,records/'increment_11_pytest.xml')
    verify_tree(ROOT)
    report={'mode':args.mode,'package_version':p2mem.__version__,'python':sys.version.split()[0],
        'tests_passed':len(cases),'historical_tests':len(cases)-len(new),'new_tests':len(new),
        'ledger_files':len(entries),'independent':independent,'comparison':comparison,'coverage':manifest['coverage'],
        'hosted_colab_execution_claim':False,'raw_regeneration_claim':False}
    (records/'increment_11_run.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return report

if __name__=='__main__':main()
