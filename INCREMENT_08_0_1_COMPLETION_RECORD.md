# Increment 8.0.1 Completion Record — Final Corrective Release

**Package:** `p2mem 0.8.1`  
**Config schema:** `8.0.1`  
**Locked scientific baseline:** Increment 7.0.4, SHA-256 `f5c9a9b50dd0edff6e5b31a42d5bba4ab23b993f5ef11c6217122b13f29d89ae`  
**Corrected predecessor:** Increment 8 ZIP, SHA-256 `68190661c521ec36c4f7e4c73030ab5a86b22ce3dd8abe6c7588d60634fa8b76`  
**Assurance:** Tier C — Screening-Level / Uncalibrated Educational  
**Increment 9:** not started

## Outcome

Increment 8.0.1 closes the final release-integrity, portability, and publication-atomicity gaps found in the overall self-audit. It does not add an NCT or overpressure model and changes no numeric scientific result.

The exact fixes are:

1. all seven upstream artifacts are bound to their approved SHA-256 values rather than merely carrying hash-shaped strings;
2. the config constructor, YAML loader, and output manifest enforce one consistent closed release policy;
3. shallow-stress, cumulative-profile, sonic/checkshot, hydrostatic, effective-stress, cross-artifact, row-count, node-coverage, and issue-inventory identities are complete;
4. the complete seven-data-plus-four-figure bundle publishes in one rollback-safe transaction;
5. the unnecessary `tests/__init__.py` import workaround is removed and the local fixture import remains safe when an unrelated external `tests` package is installed;
6. the notebook uses a verified versioned Colab tree or a fresh safe extraction without overwriting an incomplete folder;
7. Matplotlib is declared because the default workflow renders figures; and
8. the zero-count pressure table now says precisely that the **approved packaged input set** contains no calibration files.

## Verified scientific result

- Approved packaged pressure/stress calibration files: **0** across RFT, MDT, DST, FIT, LOT, XLOT, and DFIT for all four wells.
- NCT fits performed: **0**.
- Overpressure transforms performed: **0**.
- Overpressure inferences: **0**.
- Hydrostatic-reference rows: **1,053** across all four wells and three configured density scenarios.
- Effective-stress terminal scenarios: **36**, limited to Boreas 1 and Poseidon 2.
- Effective-stress profile rows: **606**.
- Extrapolated samples: **0**.

At the configured base fluid density and `alpha = 1.0`, terminal low/base/high effective vertical stress remains:

- Boreas 1: **12.0060 / 35.3860 / 58.7661 MPa**;
- Poseidon 2: **18.4633 / 43.1311 / 67.7989 MPa**.

These are uncalibrated screening scenarios, not formation-pressure measurements or operational predictions.

## Verification record

- Current tree before final packaging: **1,632/1,632 tests passed**.
- Locked Increment 1–7.0.4 subset: **1,368/1,368 passed**; all 18 locked test files are byte-identical to the baseline.
- Increment 8 subset: **264/264 passed**.
- Notebook: **33 cells**, **21 code**, **12 markdown**, **12/12 `%%writefile` byte parity**, unique IDs, valid nbformat, zero saved outputs.
- Fresh Increment 7.0.4 notebook execution: **all 21 code cells**, **25/25 gate checks PASS**.
- Final packaged-notebook execution: **all 21 code cells**, **1,632/1,632 combined tests**, **264/264 Increment 8 tests**, and **25/25 gate checks PASS**.
- Colab-bootstrap branch simulation: **PASS** for first extraction, verified-tree reuse, stale-tree preservation with clean fallback, traversal rejection, unlisted-file rejection, and unlisted-symlink rejection. The mounted-Drive interface was simulated locally; a hosted Colab execution is not claimed.
- External-`tests` collision simulation: **264/264 passed**.
- Independent, package-free numerical recomputation: **PASS**.
- Five result CSVs are byte-identical to the corrected predecessor; the approved-input inventory changes controlled wording only; the manifest changes identity/assurance text only.
- Exact delta versus Increment 7.0.4: **3 changed, 27 added, 0 removed**.
- Corrective delta versus the predecessor Increment 8 ZIP: **19 changed, 3 added, 1 removed**; the removal is the superseded `tests/__init__.py` workaround.
- No private raw inputs are packaged.
- Final archive structure: **263 safe entries**, of which **262** are covered by the current ledger and the remaining entry is the ledger itself; the ledger covers the complete regular-file set with no extras.

The final ZIP checksum is reported alongside the delivered ZIP rather than embedded here: this record is itself ledger-covered inside the ZIP, so embedding the ZIP’s own digest would create a circular hash dependency.

## Stop condition

Increment 8.0.1 is complete. Increment 9 has not been started. No elastic-property, rock-strength, horizontal-stress, mud-window, or wellbore-stability implementation is present.
