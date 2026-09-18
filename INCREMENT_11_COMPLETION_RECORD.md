# Increment 11 — Completion record

Release: p2mem 0.11.0, 8 September 2026. Project owner: Mikael Elgo.

**1,929 tests passed:** 1,852 retained historical tests and 77 Increment 11 tests. No failures, errors or skipped tests. Runtime: Python 3.12.13. The JUnit record and machine-readable run summary are in verification/.

All seven unmodified notebook code cells completed sequentially in local IPython, starting from the candidate ZIP through the notebook bootstrap, cumulative runner, QC display and results export. MODE=reproduce regenerated all seven scientific tables and both figures byte-identically. Hosted Colab and socket-backed Jupyter execution are not claimed; the verification runtime did not permit kernel sockets. Drive authentication, browser UI and Colab download behavior require the user's hosted environment.

Independent numerical verification passed on all 5,082 numeric rows and all 1,584 missing-E rows. Maximum stress residual: 1.4210854715202004e-14 MPa. The independent checker uses Decimal compliance elimination and Mohr-circle geometry, not the main stress implementation.

The dataset contains 6,666 scenario rows at 202 exact reporting nodes. Of the numeric rows, 3,175 satisfy the selected conditional fault-friction test. No row is field-stress eligible. Numeric support, conditional fault admissibility and field eligibility are deliberately separate.

The source and output content tested in the candidate release is preserved in the final release. This completion record and three static verification records were then added before final ledger creation. The run summary's ledger_files describes that candidate, not the final inventory. The final ZIP is rebuilt from the new ledger plus the ledger itself, CRC checked, and extracted through the same bootstrap. The final ZIP hash and size are outside the archive in the accompanying SHA256 file to avoid circular hashes.

The corrected Increment 10 COMPLETE baseline is retained. Its 313 ledgered files are identical except the three declared metadata files (README, package version and __init__ version). Historical scientific modules, configuration, outputs and notebooks are unchanged.

Included deliverables: executable notebook, source, configuration, seven scientific tables, two QC figures, scientific report, quickstart, manifest, independent checker, tests and release builder. Raw-source regeneration, laboratory calibration, geographic SHmax orientation and operational drilling recommendations are not claimed. Increment 12 is not implemented.
