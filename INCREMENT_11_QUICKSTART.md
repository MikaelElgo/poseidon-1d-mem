# Run Increment 11 in Google Colab

1. Upload `Poseidon_1D_MEM_Increment_11_v11.0.0.zip` to `MyDrive/Poseidon_1D_MEM/`.
2. Open `11_In_Situ_Stress_Scenarios_and_Bounds.ipynb` in Colab (available inside the ZIP and separately).
3. Choose Runtime > Run all. Authorize the Drive mount when Colab requests it.

The notebook defaults to the exact ZIP filename above, extracts to a fresh `/content` folder, and verifies every ledgered file. It installs dependencies only inside Colab and tests in an isolated copy. Existing Drive project files are not overwritten. The final cell downloads an Increment 11 results ZIP in Colab.

Use MODE=`review` to check packaged results; MODE=`reproduce` to regenerate them from packaged derived inputs and compare the scientific tables. Neither mode rereads private LAS files.

For local use, extract the entire archive and run:

    python -m pip install -e '.[dev]'
    python scripts/run_increment_11.py --mode review

For local Jupyter, set PROJECT_ROOT in the notebook to the complete extracted folder. Keep notebook edits outside the verified release folder so checksums remain valid.

The release includes 313 historical files plus the historical ledger and Increment 11 additions. See `INCREMENT_11_SHA256SUMS.txt` for the exact final inventory. Do not use an earlier Increment 10 archive as the Increment 11 ZIP.
