> **Verification repair 1:** The original exact-float strength assertion was not portable to the user's Colab runtime. The repaired verification uses explicit rounding tolerances and independently checked reproduction. See INCREMENT_12_REPAIR_1.md for current repair evidence. Original release qualification records below remain historical evidence, not proof of hosted Colab compatibility.

# Increment 12 completion record

Qualified 8 September 2026, using the runtime recorded in verification/increment_12/qualified_runtime.json.

- 1,929 historical tests passed on the exact checksum-restored Increment 11 baseline.
- 61 Increment 12 tests passed on the current release candidate. No test failures, errors or skips.
- All seven unmodified notebook code cells completed in local IPython, in reproduce mode, using the candidate ZIP through the notebook's embedded extraction bootstrap.
- Five CSVs, the PNG figure and the output manifest reproduced byte-for-byte (seven files).
- Independent checks passed for 546 analytical vertical intervals, 28,590 wall-state records and 3,491 supported intervals on a separate 0.25-degree angular grid.
- 3,822 orientation cases comprise 3,491 intervals and 331 empty sets. All passed angular refinement. No field eligibility is claimed.
- ZIP construction uses standard DEFLATE, includes the checksum ledger, rejects unsafe paths, checks CRCs, and extracts its actual finished bytes through the notebook bootstrap before publishing the archive.

The JSON/XML/log records preserve the exact candidate evidence. Their candidate ledger count and ZIP hash identify that test input. The final package subsequently adds these records, this completion note, and the qualified-runtime note; scientific code, data, configuration and notebook bytes remain those tested. The final archive has its own separately supplied whole-file SHA-256 record and is subjected to the release round-trip checks after packaging. A whole-archive digest is not embedded inside that archive because doing so would be self-referential.

This verifies local code-cell execution, not hosted Colab UI/runtime execution. Reproduction uses packaged derived inputs, not a fresh ingestion of private raw LAS files. The scientific report documents the analogue, orientation, boundary and finite-angle limitations.
