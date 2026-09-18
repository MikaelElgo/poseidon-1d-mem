# Increment 10 Completion Record

**Status:** complete  
**Package:** Poseidon 1D MEM v0.10.0  
**Baseline:** Increment 9 ledger SHA-256 `da9b90269787b13e45738d8c7442abd051a2f1d48045284863bb93273c94db47`

Increment 10 implements the static-mechanics and rock-strength scenario layer described in the scientific report. It produces four retained-row reference profiles, seven explicit parameter scenarios, coverage and interval summaries, method applicability controls, and four QC figures. The outputs are analogue calculations with explicit provenance and withheld field eligibility.

Verification completed on the cumulative package:

- **1,852 tests passed**: 1,754 historical tests and 98 Increment 10 tests.
- Independent Decimal-based checker: **80 rows** across the four wells; maximum absolute residuals were below `3e-14` for the analogue equations and below `4e-15` for the Mohr-circle checks.
- Analogue numeric coverage: Boreas 1 **388**, Poseidon 2 **1,739**, Poseidon North 1 **3,428**, Proteus 1ST2 **290** rows; total **5,845**.
- Field-mechanics eligible rows: **0**.
- Baseline ledger inventory: **282** entries; Increment 10 release inventory is recorded in `INCREMENT_10_SHA256SUMS.txt`.
- Python runtime used for verification: **3.12.13**.

The release does not reread raw source files, does not claim hosted Colab execution, and does not convert analogue outputs into calibrated or field-eligible properties. The final ZIP hash is supplied in the accompanying `Poseidon_1D_MEM_Increment_10_v10.0.0_SHA256.txt` file to avoid a circular checksum.
