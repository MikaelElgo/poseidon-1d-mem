# Increment 9 — start here

1. Upload `Poseidon_1D_MEM_Increment_09.zip` to `My Drive/Poseidon_1D_MEM/`.
2. Open `09_Dynamic_Elastic_Properties_and_QC.ipynb` in Google Colab.
3. Keep `MODE = "review"` for the first run and select **Runtime → Run all**.
4. Allow Drive access when Colab asks. The notebook extracts a separate verified
   working copy under `/content`, checks the files and runs the full tests in a
   disposable copy so earlier integration tests cannot change the release.
5. Read the coverage tables and four QC figures. The last cell saves a results
   ZIP into `My Drive/Poseidon_1D_MEM/` with a unique timestamp.

You do not need to extract or execute increments 6, 7 or 8. This is a cumulative
package. Keep the original release ZIP unchanged. Do not overlay different
increment folders.

If your ZIP is elsewhere, put its exact path in the notebook's `ZIP_PATH` setting.
If both default locations contain a ZIP, choose one explicitly with `ZIP_PATH`.
The notebook prints its SHA-256 so you can compare it to the completion record.

Review mode validates the delivered files and tests. It does not re-read the
private measurements. To recalculate from those measurements, select
`MODE = "regenerate"` and set `PRIVATE_INPUT_ROOT` to a folder with:

| Subfolder | Required filenames |
|---|---|
| `las` | `Boreas_1_logs.las`, `Poseidon_2_logs.las`, `Poseidon_North_1_logs.las`, `Proteus_1ST2_logs.las` |
| `deviation` | `Boreas 1_dev.txt`, `Poseidon 2_dev.txt`, `Poseidon North 1_dev.txt`, `Proteus 1ST2_dev.txt` |

Only the approved source bytes pass the existing contracts. Regenerated outputs
go into a separate local output folder and are compared with the packaged
scientific results. Missing sources stop regeneration with an error.

For local Python/Jupyter, set `PROJECT_ROOT` to a fresh extraction. Install with
`python -m pip install -e ".[dev]"` from that folder and run:

```bash
python scripts/run_increment_09.py --mode review
```

Local regeneration uses the same command with
`--mode regenerate --private-input-root /your/private_inputs`.

These are dynamic isotropic screening estimates. No calibrated static moduli,
rock strength or horizontal stresses are supplied by Increment 9. Sparse
coverage is retained as missing data. Primary Poisson/bulk/Young estimates use
the existing ratio screen; negative Poisson diagnostics remain separately
identified. The plots zoom to intervals with available estimates.
