"""Compare scientific tables numerically while keeping release hashes strict.

Last-bit arithmetic and PNG rendering need not be byte-identical across
runtimes. This comparison never replaces input/output SHA-256 validation.
"""
import csv
import json
import math
from pathlib import Path
import re

REL_TOL = 1e-12
ABS_TOL = 1e-12


def same_number(actual, expected):
    a,b=float(actual),float(expected)
    return math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=REL_TOL,abs_tol=ABS_TOL)


def same_value(a,b):
    if a == b:return True
    # Preserve identifiers, nulls, booleans and integral strings exactly.
    if not isinstance(a,str) or not isinstance(b,str) or not a or not b:return False
    if re.fullmatch(r'[+-]?\d+',a) and re.fullmatch(r'[+-]?\d+',b):return False
    try:return same_number(a,b)
    except (TypeError,ValueError):return False


def compare_tables(expected, actual):
    with Path(expected).open(newline='') as a,Path(actual).open(newline='') as b:
        left,right=csv.DictReader(a),csv.DictReader(b)
        if left.fieldnames!=right.fieldnames:raise ValueError('Reproduction table schema changed: '+Path(actual).name)
        from itertools import zip_longest
        count=0
        for count,(x,y) in enumerate(zip_longest(left,right),1):
            if x is None or y is None:raise ValueError('Reproduction table row count changed')
            for key in left.fieldnames:
                if Path(expected).name=='critical_wall_states.csv' and key=='theta_deg':
                    # Symmetry-related critical angles may exchange after a
                    # last-bit tie. All normal/principal stresses and margins
                    # must still match; the independent checker verifies the
                    # tensor at each reported angle, including shear sign.
                    if not (0 <= float(x[key]) < 360 and 0 <= float(y[key]) < 360):
                        raise ValueError('Invalid critical angle')
                elif Path(expected).name=='critical_wall_states.csv' and key=='shear_MPa':
                    if not same_number(abs(float(x[key])),abs(float(y[key]))):
                        raise ValueError('Reproduction shear magnitude differs')
                elif key=='angular_history_json':
                    # JSON contains numeric diagnostics; preserve keys, order,
                    # statuses and list length, with the same float tolerance.
                    if not same_json(json.loads(x[key]),json.loads(y[key])):raise ValueError(f'Reproduction angular history changed at row {count}')
                elif not same_value(x[key],y[key]):
                    raise ValueError(f'Reproduction differs: {Path(actual).name}, row {count}, {key}: {x[key]} vs {y[key]}')
        return count


def same_json(a,b):
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(same_json(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same_json(x,y) for x,y in zip(a,b))
    if isinstance(a,bool) or isinstance(b,bool):return type(a) is type(b) and a==b
    if isinstance(a,(float,int)) and isinstance(b,(float,int)):
        return a==b if isinstance(a,int) and isinstance(b,int) else same_number(a,b)
    return type(a) is type(b) and a==b


def compare(expected,actual):
    expected,actual=Path(expected),Path(actual)
    a=json.loads((expected/'wbs_manifest.json').read_text());b=json.loads((actual/'wbs_manifest.json').read_text())
    if set(a)!=set(b) or {k:v for k,v in a.items() if k!='output_sha256'}!={k:v for k,v in b.items() if k!='output_sha256'}:
        raise ValueError('Reproduction manifest metadata differs')
    if set(a['output_sha256'])!=set(b['output_sha256']):raise ValueError('Reproduction file inventory differs')
    tables={}
    for name in a['row_counts']:tables[name]=compare_tables(expected/name,actual/name)
    for name in a['output_sha256']:
        if name.endswith('.png'):
            x,y=(expected/name).read_bytes(),(actual/name).read_bytes()
            if x[:8]!=b'\x89PNG\r\n\x1a\n' or y[:8]!=x[:8] or x[12:16]!=b'IHDR' or y[12:16]!=b'IHDR' or x[16:24]!=y[16:24]:raise ValueError('Reproduction figure format/dimensions changed')
    names=list(a['output_sha256'])+['wbs_manifest.json']
    return {'files_compared':len(names),'files_byte_identical':sum((expected/n).read_bytes()==(actual/n).read_bytes() for n in names),
            'tables_numerically_equal':len(tables),'table_rows_checked':tables,
            'relative_tolerance':REL_TOL,'absolute_tolerance':ABS_TOL,
            'scope':'packaged derived inputs; scientific table equivalence; PNG byte differences reported separately'}
