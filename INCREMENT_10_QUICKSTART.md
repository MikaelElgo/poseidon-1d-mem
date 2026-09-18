# Increment 10 - Start here

1. Put `Poseidon_1D_MEM_Increment_10.zip` in `My Drive/Poseidon_1D_MEM/`.
2. Open `10_Static_Mechanics_and_Rock_Strength_Scenarios.ipynb` in Google Colab.
3. Keep `MODE = "reproduce"`. If your ZIP has a different filename, set `ZIP_PATH`
   to its exact Drive path. Leave `PROJECT_ROOT` empty in Colab.
4. Select **Runtime > Run all** and allow the requested Drive mount.
5. The notebook extracts a fresh working copy, installs the declared dependencies,
   reproduces the mechanics experiment, performs independent checks and runs the
   full suite in a disposable copy. The long verification cell prints its results
   when the test subprocess finishes; allow several minutes on Colab.
6. Read the coverage table before the figures. The final cell saves a timestamped
   results ZIP in `My Drive/Poseidon_1D_MEM/`.

**No additional raw-data upload is required for this increment.** The workflow
reuses the verified, derived Increment 9 profiles. It does not claim to have
re-read the private LAS or survey measurements.

## What WITHHELD means

All field-mechanics eligibility remains withheld because material applicability
and local static/strength calibration are absent. Software checks can pass while
field methods remain withheld. Finite columns ending in `scenario` or `assumed`
are hypothetical analogue experiment outputs, not field-approved estimates.

The static relation is restricted to the source's Edyn predictor span. An empty
cell means no output is supported by this experiment, never zero strength.

## Output layout

- Four `*_mechanics.csv` files: reference experiment, every original sample,
  missing values preserved, explicit evidence and field eligibility columns.
- `mechanics_summary.csv`: seven one-at-a-time experiment cases, each property's
  min/median/max and median change; no statistical uncertainty interpretation.
- `mechanics_coverage.csv`: missing input, predictor-range exclusion and numeric
  support counts with original sample denominators.
- `formation_interval_summary.csv`: supported marker pairs only, with inherited
  depth and well-identity status. These are not new lithology interpretations.
- `method_applicability.csv`: current field blockers and rejected candidate methods.
- Four QC figures; one complete output manifest.

Full non-reference profiles are reproducibly calculated by `evaluate_mechanics`
with the selected case in `config/mechanics_scenarios.json`. The summary tables
already evaluate all seven cases. This avoids storing seven identical copies
of unchanged E/UCS/depth columns. The configs identify the experiment; do not
edit a reviewed release in place. New experiments need a separate version.

## Local use

From a fresh extraction:

```bash
python -m pip install -e ".[dev]"
python scripts/run_increment_10.py --mode reproduce
```

Use `--mode review` to verify the packaged results without publishing a
reproduced bundle. Both modes run the full tests and independent checks.
Reproduced outputs go to `outputs/10_static_mechanics_strength_regenerated`.

Do not overlay increment folders or rerun notebooks 1-9 in this working tree.
They are immutable historical records. Keep the original source ZIP unchanged.
