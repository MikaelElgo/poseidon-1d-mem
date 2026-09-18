# Increment 6.1.4 Manifest — Completing the Increment 6.1.3 Architecture

**Project:** Poseidon 2 — 1D Mechanical Earth Model
**Assurance tier:** Tier C — Screening-Level / Uncalibrated Educational (unchanged)
**Package version:** `p2mem` 0.6.4 → **0.6.5**
**Baseline:** `Poseidon_1D_MEM_Increment_06_v6.1.3.zip`, SHA-256 `d511dbcbdd4ec50ff8bf96eda67b54be50b818649a27d02722e0e12edad7ea3b` — **independently recomputed before any change; exact match.** Extracted fresh.

**Baseline suite re-run before any change: 782 passed.**

**Scope: one scope rule. Nothing else.** No scientific threshold, tolerance, endpoint scenario, contiguity policy, GR disposition, depth-mapping rule, or real-data interpretation was altered. No runtime dependency added — **NumPy and PyYAML remain the only two.** **All twelve outputs and figures are byte-identical to Increment 6.1.3.**

**Increment 7 has NOT been started.**

---

## 1. The finding — self-identified, and the same shape as the two before it

Increment 6.1.3 replaced grammar with membership, and its own manifest argued that a finite list is not a closed rule. It then closed only **three of four** scopes that way. Explanatory scope was still decided by a finite list of *project-reference* tokens: a rock name was admitted whenever the sentence appeared to mention none of this project's wells or rock bodies.

That is the same shape of rule as the two that had just been deleted, and it failed the same way. Reproduced against the unmodified 6.1.3 baseline:

| Explanatory text | 6.1.3 | 6.1.4 |
|---|---|---|
| The member is shale. | **PASSED** | **VIOLATION** |
| The group is limestone. | **PASSED** | **VIOLATION** |
| The package is a clean sandstone. | **PASSED** | **VIOLATION** |
| The play is shale-dominated. | **PASSED** | **VIOLATION** |
| The prospect is carbonate. | **PASSED** | **VIOLATION** |
| The target is sandstone. | **PASSED** | **VIOLATION** |
| The upper member is a clean sandstone reservoir. | violation | violation |

**The last row is the instructive one.** It failed under 6.1.3 *only* because `reservoir` happened to be in the token list while `member` was not — an accident of vocabulary, not a judgement about geology. `member` and `group` are formal lithostratigraphic ranks; `play`, `prospect` and `target` are the words an exploration report actually uses. Any of them would have carried an assertion straight through.

This was found by continuing to audit the patch after it was delivered, not reported by a reviewer. It is recorded here as a defect of Increment 6.1.3, which claimed the architecture was complete when one scope still carried the rule it was replacing.

## 2. The correction — invert the rule, delete the lists

Explanatory scope is now identical in kind to `SCOPE_METHOD`:

> Text carrying no prohibited term needs no adjudication. Text that carries one is a violation **unless the text equals a member of the closed `GENERIC_EXPLANATORY_STATEMENTS` registry**.

It **fails closed**. An unrecognised construction is refused rather than admitted, so no gap in any vocabulary can let an assertion through — because nothing is admitted by how it reads.

`PROJECT_WELL_NAME_TOKENS`, `PROJECT_ROCK_BODY_TOKENS` and `PROJECT_REFERENCE_TOKENS` are **deleted**, and `test_no_project_reference_token_list_survives` asserts none is importable. Nothing in the validator now enumerates what a project reference looks like.

### 2.1 The final scope model — all four closed

| Scope | Rule | Decidable by |
|---|---|---|
| `SCOPE_LABEL` | any prohibited token violates | token membership |
| `SCOPE_INTERPRETIVE` | zero allowance | token membership |
| `SCOPE_METHOD` | text must equal a `METHOD_STATEMENTS` member | exact equality |
| `SCOPE_EXPLANATORY` | rock term violates unless text equals a `GENERIC_EXPLANATORY_STATEMENTS` member | exact equality |

No scope is decided by grammar, by a window, or by a vocabulary of things that *look like* a reference.

### 2.2 The generic registry is empty — measured, not omitted

This project persists exactly **one** field in explanatory scope: `manifest.named_lithology_statement`. It carries **no prohibited term at all**, so it passes without any registry entry, and the registry is empty.

The mechanism is nevertheless live and tested, because a later increment explaining gamma-ray non-uniqueness may genuinely need to write *"a clean sandstone and a clean limestone read alike on GR"*. Two tests register a statement via `monkeypatch` and prove the registry admits the exact text, refuses a near-miss and a case change, and reports any term the entry did not declare. An empty registry must not be allowed to hide a broken mechanism.

### 2.3 Disclosed cost

Legitimate generic science now requires a registry entry. That friction is the mechanism, not a side effect: it converts an unbounded judgement, made silently on every string, into a finite decision made once and reviewed. `test_unregistered_explanatory_rock_names_fail_closed` asserts this by putting two genuinely sensible generic sentences in the same parametrized list as the six gap cases — under a registry rule they are the same case, which is exactly the point.

## 3. Non-regression

Every mandated real-data value re-measured and unchanged: Boreas 1 ECGR median 8.3968 API, 4 negative / 42 zero / 2,059 above seabed, 0 endpoints / 0 proxies / 0 lithology-dependent masks; Vp/Vs regimes 0/1, 0/22, 4/3, 0/3; interval register 5,857 rows, 327 interrupted blocks, 443 gaps, 666 bridged samples, 85 blocks with ≥2 gaps, max 5; Poseidon 2 gross 144.42–1,159.22 m (×8.03) and strict-no-gap 140.00–1,110.24 m (×7.93); `n_extrapolated` 0 for every well; named lithology **false**, 143 fields checked, 0 violations.

**All 12 outputs and figures are byte-identical to Increment 6.1.3.** Unlike 6.1.3, no field enters or leaves the validated scope, so `n_fields_checked` remains 143 and the manifest itself is unchanged. This was predicted before the code was written.

## 4. Exact packaged delta — Increment 6.1.3 → Increment 6.1.4

**Changed — 6 files:** `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb`, `README.md`, `p2mem/__init__.py`, `p2mem/wellframe_models.py`, `pyproject.toml`, `tests/test_petrophysics.py`.

**Added — 2 files:** `INCREMENT_06_1_4_MANIFEST.md`, `INCREMENT_06_1_4_SHA256SUMS.txt`.

**Removed — 0. Total path differences — 8.** No output, no figure, no config, and no other module changed. The authoritative measurement from the final ZIP is in the completion record §4.

**Locked-baseline audit:** of the 150 files inherited from Increment 5.1.2, exactly three differ — `pyproject.toml`, `p2mem/__init__.py`, `README.md` — the three historically permitted additive metadata files.

## 5. Test suite

| | Count |
|---|---|
| Increment 6.1.3 baseline, re-run before any change | **782 passed** |
| After Increment 6.1.4 | **795 passed** (0 failed, 0 errors, 0 skipped) |
| Net change | **+13** — `tests/test_petrophysics.py` 137 → 150 |

Three pre-existing tests were **rewritten to the new contract**: the two that asserted unregistered generic examples pass, and the one that asserted the project-reference rule. They now assert the inverted rule, and the sentences they used are retained inside the fail-closed parametrization rather than deleted. Added: the six reproduced gap cases, the registry-mechanism tests, the token-list deletion test, and a closure proof over explanatory scope.

**Closure now covers all four scopes.** The explanatory proof runs every prohibited term through twelve carriers — including all six stratigraphic and exploration nouns the 6.1.3 list omitted — for **336 enumerated cases**, alongside the 462-case interpretive proof and the label proof.

## 6. Notebook

73 cells (38 code), unique IDs, zero saved outputs, `nbformat.validate()` passes, **14/14 `%%writefile` parity**, 38/38 cells execute from a fresh `/content`-style root, internal pytest **795 passed**, **20/20 gate checks `[PASS]`**.

The gate count is unchanged at 20, but one check is strictly stronger: *"Closure holds in EVERY scope for EVERY prohibited term and carrier"* now runs the explanatory carriers as well, and the registry check additionally asserts the generic registry is empty and that both a stratigraphic-noun assertion and a plain generic example are refused.

## 7. Assurance classification

Unchanged: **Tier C — screening-level, uncalibrated, educational.** No calibration evidence added, no physical quantity computed, no assurance level raised.

## 8. Stop condition

Increment 6.1.4 is complete as of this manifest. **Increment 7 has not been started.**
