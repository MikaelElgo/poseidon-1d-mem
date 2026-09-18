# Increment 11 Manifest

Release: Poseidon 1D MEM Increment 11, p2mem 0.11.0. Project owner: Mikael Elgo.

Scope: conditional horizontal-stress scenarios, explicit depth alignment, inherited vertical-stress partitions, fault-friction bounds, regime labels and formation context. Source equations and restrictions are in `config/horizontal_stress_methods.json` and the scientific report.

Inputs: verified Increment 10 COMPLETE cumulative release. All historical modules, notebooks, configuration and outputs are preserved byte-for-byte. Only the three public metadata files README.md, pyproject.toml and p2mem/__init__.py change.

Added implementation: `p2mem/horizontal_stress.py`, `p2mem/io/stress_workflow.py`, two configuration JSON files, an independent checker, a safe bootstrap, a runner, a complete release builder, three test modules and the Increment 11 notebook. `outputs/11_horizontal_stress/` contains seven scientific tables, two QC figures and a provenance manifest. The report and quickstart explain use and limitations.

The ZIP includes its own `INCREMENT_11_SHA256SUMS.txt` (the ledger does not hash itself). Runtime caches, logs, editable notebooks and regenerated comparison folders are excluded. Verification reports are static evidence; runtime outputs are written under run_records.

All field stress eligibility flags are false. No SHmax geographic orientation, calibrated field stress, predicted field pressure, or operational mud-weight recommendation is produced. Increment 12 has not been implemented.
