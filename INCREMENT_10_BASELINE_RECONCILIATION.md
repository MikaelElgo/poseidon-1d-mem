# Continuation baseline and Increment 7 archive reconciliation

## Chosen continuation baseline

The supplied `Poseidon_1D_MEM_Increment_09(1).zip` is the baseline:

`53bf68019b3c0226e8e0fcfafa070d3e7ef42f6e4292e84aba8c16e4dc600259`

It contains 283 entries. All 282 non-self ledger entries matched their hashes.
A fresh local review run on Python 3.12.13 observed **1,754 passing tests**,
including 1,632 tests inherited through Increment 8 and 122 Increment 9 tests.
The runner validated the serialized elastic bundle and preserved release bytes
by running tests in a disposable copy. Raw-source regeneration was not performed.

The supplied Increment 8 ZIP matches the baseline stated in Increment 9:

`ad6ef2ece0937203baee582e9be67950a8b4ca78176bdd21ac7e187d1d63bd7c`

## Increment 7 discrepancy

Supplied Increment 7 ZIP:

`a798fd977cb3649a4e0a573b0cdbad3a8dd26b84aa6f373aa88e6c495f6f945e`

Increment 7 ZIP identified as the predecessor in the Increment 8 records:

`f5c9a9b50dd0edff6e5b31a42d5bba4ab23b993f5ef11c6217122b13f29d89ae`

These archive identities differ. The attached Increment 7 bytes are not silently
asserted to match the recorded predecessor.

The direct comparison of supplied 7 files against their cumulative copies in 8
found five changed paths:

- `07_Density_QC_and_Overburden_Stress_Framework.ipynb`
- `INCREMENT_07_0_4_SHA256SUMS.txt`
- `README.md`
- `p2mem/__init__.py`
- `pyproject.toml`

In the notebook, cells 15 and 17 have version headings corrected from 0.7.3 to
0.7.4. Cell 85 has an additional repeated `OverburdenInputError` import. The
notebook ledger consequently differs. The last three files are the expected
version/narrative changes when progressing to 8.

All other shared files, including the scientific modules, configurations, tests
and result artifacts, were byte-identical in that comparison. This bounds the
observed discrepancy to packaging/notebook history rather than demonstrating a
numerical science defect. The missing predecessor ZIP was not reconstructed.

## Resolution for this release

Continue from the hash-verified cumulative Increment 9 package, not an overlay
of separate 7/8 folders. Preserve all historical manifests and notebooks as
records, including their original predecessor statements. This note records the
discrepancy explicitly; it does not retrospectively claim an archive match.
Only the current README and two package-metadata files are changed from 9.
