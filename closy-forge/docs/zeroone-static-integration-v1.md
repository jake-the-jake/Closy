# ZeroOne static integration v1

Closy owns the canonical garment package. ZeroOne is an optional, derivative-only,
headless CPU processor. This integration never commits a private native executable and never
replaces the conventional `render/fallback.glb` asset.

## Tool contract

Configure `CLOSY_ZEROONE_PROCESS` or pass `--executable`, and separately configure
`CLOSY_ZEROONE_TRUSTED_BUILD_RECORD` or pass `--trusted-build-record`. The resolver hashes the
executable itself, compares it with the independently captured build record, then runs
`version-json` and cross-checks source, compiler, build type, schemas, profile, and headless CPU
flags. A caller-supplied hash alone is never trusted. Missing or incompatible tools return an
explicit unavailable result and leave the package untouched.

The active candidate-static source pin for this vertical is
`13a844d240f4bbb2cafde105c4a0bdca8d89a06b` from unmerged ZeroOne PR #2. Its exact raw head passed
the bounded Windows and Ubuntu standalone CPU workflow in run `33187775880`; the private Windows
artifact is independently hash-bound to executable SHA-256
`59bb051455ae2878a30edd353bdb451271107bb5df3e3570b89b955379cf2065`. This is candidate-branch
evidence, not current-mainline qualification. Native executable bytes are never stored in Closy.

## Execution and authority

`closy-forge zeroone static` performs these bounded steps:

1. validate the canonical `.closygarment` package;
2. generate a request naming exact package-relative assets and hashes;
3. run `inspect`, a cache-miss `cook`, a cache-hit `cook`, and `validate`;
4. repeat the clean cook/validation in a second output root;
5. compare every declared canonical derivative byte hash;
6. verify pattern, simulation, binding, source, appearance, and fallback hashes before/after;
7. import only exact-manifest regular files through no-follow same-handle validation;
8. publish the accepted derivative through marker-owned staging only under `zeroone/static-d0`;
9. rerun ordinary package validation, including the optional namespace validator.

The package manifest and all inventoried canonical assets remain byte-identical. The optional
namespace contains the request, processing/validation reports, compatibility metadata,
provenance, source-to-derivative hashes, and native derivative. Deleting that namespace does
not remove any garment authority.

## Evidence boundary

The refreshed report executes all nine predeclared project-authored synthetic garment families
with a private authenticated candidate-static binary. Each family proves clean/cache agreement,
namespace deletion/rebuild, and independent V3 page-byte decode with deterministic four-view
machine review. Human visual review remains not run, and the paired Closy execution remains local
candidate evidence rather than durable current-mainline qualification. Global Phase 10 remains
partial without current-master pairing, human review, mobile, dynamic, private-user and production
provider evidence.
`C3-Binding-D0` plus refreshed paired scoped Z1 permits only a mechanical/reference Phase 11
slice; `PHY1-SingleLayer-D0` remains required for solver-driven physical-quality claims.
