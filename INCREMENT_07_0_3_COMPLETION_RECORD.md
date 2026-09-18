# Increment 7.0.3 Completion Record — Closed P05 Scenario-Percentile Contract

**Baseline:** `Poseidon_1D_MEM_Increment_07_v7.0.2.zip`, SHA-256
`3f18d6bd7266f1ca3e0b3ccf0810a776bb76547b04e4c6e627bae9a6748be949`,
recomputed and matched exactly before modification. **Version:** `p2mem 0.7.3`.
**Scope:** one configuration-to-computation provenance correction only.
**Increment 8 has not been started.**

## Corrected finding

The high shallow-column scenario always consumed the stored same-well P05 density, but
the configuration accepted any percentile in `(0, 100)`. A synthetic reproduction showed
that configurations labelled 5, 50, and 95 all returned 1575 kg/m3 while the actual P05,
P50, and P95 were 1575, 2250, and 2925 kg/m3. The calculation was fixed to P05; the
advertised configurability was false.

Both YAML loading and the public frozen `OverburdenConfig` constructor now require
`scenario_high_percentile` to equal exactly 5.0. Ten regression cases test five invalid
values through both entry points. The packaged configuration already used 5.0, so no
approved scientific value changes.

## Verification results

- **1,316/1,316 tests passed**: 944 locked pre-Increment-7 tests plus 372 Increment 7
  tests; 10 cases were added to the 1,306-test direct baseline.
- Notebook: 86 cells, 86 unique IDs, zero saved outputs, valid nbformat, 17/17
  `%%writefile` parity, and 39 declared gate checks including a live invalid-percentile
  constructor probe.
- Package delta: 8 changed, 3 added, 0 removed; every other baseline file is
  byte-identical.
- Scientific outputs: **13/13 byte-identical** to Increment 7.0.2. No value, threshold,
  status, scenario, CSV/JSON result, or figure changed.
- Clean-room ZIP safety, checksum verification, offline editable installation, full and
  partitioned test runs, direct loader/constructor probes, notebook checks, path and
  private-data scans, and locked-baseline comparisons passed.

The full real-data notebook was not re-executed because private raw project inputs are not
part of the package and were unavailable here; no Colab execution is claimed. This does
not weaken the patch-specific result: both changed enforcement paths, their notebook gate
probe, all source parity, and the unchanged packaged scientific outputs were verified.

The final ZIP hash is reported externally with the delivered package because embedding a
ZIP's own hash inside one of its members would be self-referential.
