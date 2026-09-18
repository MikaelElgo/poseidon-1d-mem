# Increment 12 manifest

This is a complete cumulative release based on the verified Increment 11 ZIP. The Increment 12 ledger covers all deliverable files; the ledger itself is included in the ZIP but is not self-hashed. The separately delivered SHA-256 record identifies the complete archive.

New science: `p2mem/wellbore_stability.py` and `p2mem/io/wbs_workflow.py`.

New controls: `config/wellbore_stability.json`.

New outputs: `outputs/12_wellbore_stability/` (five CSVs, a QC figure, a hash manifest).

New execution: `12_Wellbore_Stability_Envelopes.ipynb`, `scripts/run_increment_12.py`, `scripts/bootstrap_increment_12.py`, `scripts/build_increment_12_release.py` and `scripts/verify_increment_12_independent.py`.

New tests: `tests/test_wellbore_stability.py`, `tests/test_wbs_workflow.py`, `tests/test_increment12_release.py`.

New documentation: Increment 12 scientific report, quickstart, manifest and completion record. Verification evidence is under `verification/increment_12/`.

All Increment 11 files remain byte-identical except README.md, pyproject.toml and p2mem/__init__.py. Exact copies of those three files are under `verification/increment_11_metadata/`, and the original Increment 11 ledger verifies the restored historical baseline. Existing notebooks, scientific modules, configurations, tests and results are unchanged.

The notebook is stored unexecuted. Running it creates run_records and optional regenerated outputs that are not part of the release ledger. Original ledger-covered outputs are never overwritten by reproduce mode.
