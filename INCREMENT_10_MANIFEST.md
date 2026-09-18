# Poseidon 1D MEM — Increment 10 Manifest

Package version: **0.10.0**  
Baseline: Increment 9 cumulative release, ledger SHA-256 `da9b90269787b13e45738d8c7442abd051a2f1d48045284863bb93273c94db47`.

Increment 10 adds a controlled static-mechanics and rock-strength scenario layer over the packaged Increment 9 dynamic-elastic outputs. It includes the `p2mem.mechanics` model, scenario configuration, reproducible workflow, QC figures, notebook, scientific report, baseline reconciliation, tests, and generated tables under `outputs/10_static_mechanics_strength/`.

The release preserves original sample rows and missingness. Numeric results are conditional analogues only: `E_static = 0.3655 E_dynamic^1.0959` is evaluated only over the reviewed source span (17.90–43.45 GPa); UCS uses `46.2 exp(0.027 E_static)`; isotropic moduli and Mohr–Coulomb parameters are scenario calculations. No lithology inference, calibration claim, or field-mechanics eligibility is made. Every field eligibility flag is false.

The workflow verifies the Increment 9 ledger before reading packaged derived inputs, supports review and reproduction modes, publishes atomically, and rejects unsafe or mismatched ledgers. Raw LAS files are not included or reread. Hosted Colab execution is not claimed.

Release contents are enumerated in `INCREMENT_10_SHA256SUMS.txt`. Runtime logs, caches, and regenerated comparison directories are excluded from the release ledger.
