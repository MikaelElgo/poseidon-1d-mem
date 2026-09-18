# Increment 12 quickstart

## Google Colab

1. Upload `Poseidon_1D_MEM_Increment_12_v12.0.0.zip` to `MyDrive/Poseidon_1D_MEM/` without extracting it.
2. Open `12_Wellbore_Stability_Envelopes.ipynb` in Colab.
3. Leave MODE as `review` to verify packaged results, or set it to `reproduce` to regenerate them as well.
4. If you used another location, set ZIP_PATH to the exact path. Leave PROJECT_ROOT empty for normal ZIP use.
5. Run all cells. The notebook mounts Drive, verifies the ledger and every file, extracts into a fresh directory, installs dependencies, runs checks and exports results.

The ZIP contains the ledger at its top level and uses standard ZIP DEFLATE with Windows-compatible paths. Do not use an Increment 10/11 archive with this notebook. A missing ledger or changed file is an incomplete/incorrect release and is not bypassed.

## Local Python

Extract the complete archive to a new directory and run from that directory:

```bash
python -m pip install -e '.[dev]'
python scripts/run_increment_12.py --mode review
python scripts/run_increment_12.py --mode reproduce
```

The supported verification entry point is the runner above. Historical release tests run against the restored exact Increment 11 baseline; current tests run against Increment 12. A flat `pytest` across old release packagers is not the version-scoped verification workflow.

The notebook supports `P2MEM12_ZIP_PATH`, `P2MEM12_PROJECT_ROOT` and `P2MEM12_MODE` environment overrides for unattended local cell execution. The scientific runner needs NumPy, PyYAML, matplotlib and pytest. A local notebook front end additionally needs Jupyter/IPython. Python 3.12 was used for release verification; the inherited project metadata states >=3.9 but other interpreter versions were not separately qualified.

## Where to look

- `outputs/12_wellbore_stability/pressure_envelopes.csv`: intervals, empty sets and convergence diagnostics.
- `outputs/12_wellbore_stability/wbs_input_eligibility.csv`: all source inputs and exclusion reasons.
- `INCREMENT_12_SCIENTIFIC_REPORT.md`: equations, boundary assumptions, source references and limitations.
- `run_records/increment_12_run.json`: current run's test and independent-check evidence.

All field-eligibility flags remain false. These analogue-based hypothetical orientation experiments do not establish a recommended mud weight.

## Qualified reproduction environment

Exact reproduction was checked on Linux x86_64 with Python 3.12.13, NumPy 2.3.5, matplotlib 3.10.8, PyYAML 6.0.3 and pytest 9.1.1. Versions are recorded in `verification/increment_12/qualified_runtime.json`. Strict byte comparison can detect differences caused by another numerical or rendering environment. Review mode verifies packaged bytes and scientific checks without requiring rerendered figures to match. Hosted Colab was not executed during qualification.

## Verification repair 1

The original strength-provenance test used exact equality for values recomputed by floating-point arithmetic. The repair uses relative and absolute tolerances of 1e-12 for those values, while keeping original sample IDs, scenario IDs, inherited depth/stress strings, missing values and eligibility flags exact. A 1e-6 MPa change is still rejected.

Reproduction compares numeric tables with explicit tolerances and reports byte matches separately; regenerated outputs retain their own strict hashes and pass independent scientific verification. PNG rendering differences alone no longer stop reproduction. Download the repaired ZIP again, replace the previous Drive copy, and run the accompanying notebook from the beginning. The release filename is retained so the existing ZIP_PATH remains valid.
