# ZeroOne static integration v1

Closy owns the canonical garment package. ZeroOne is an optional, derivative-only,
headless CPU processor. This integration never commits a private native executable and never
replaces the conventional `render/fallback.glb` asset.

## Tool contract

Configure `CLOSY_ZEROONE_PROCESS` or pass `--executable`. The resolver hashes the executable,
runs `version-json`, and requires the pinned ZeroOne source SHA, a clean source build, the
versioned request/report schemas, the `closy-static-d0-cpu-v1` profile, and headless CPU flags.
`CLOSY_ZEROONE_EXECUTABLE_SHA256` or `--expected-executable-sha256` can pin the local build
bytes as well. Missing or incompatible tools return an explicit unavailable result and leave
the package untouched.

The source pin for this vertical is
`c6388cbbf53ba8a47831ec25e83808e1edf32194` from draft ZeroOne PR #1. Native executable bytes
are toolchain-specific and are therefore recorded in execution evidence rather than stored in
Closy.

## Execution and authority

`closy-forge zeroone static` performs these bounded steps:

1. validate the canonical `.closygarment` package;
2. generate a request naming exact package-relative assets and hashes;
3. run `inspect`, a cache-miss `cook`, a cache-hit `cook`, and `validate`;
4. repeat the clean cook/validation in a second output root;
5. compare every declared canonical derivative byte hash;
6. verify pattern, simulation, binding, source, appearance, and fallback hashes before/after;
7. publish the accepted derivative only under `zeroone/static-d0`;
8. rerun ordinary package validation, including the optional namespace validator.

The package manifest and all inventoried canonical assets remain byte-identical. The optional
namespace contains the request, processing/validation reports, compatibility metadata,
provenance, source-to-derivative hashes, and native derivative. Deleting that namespace does
not remove any garment authority.

## Evidence boundary

This closes only the exact tested D0 CPU/static profile when real compiled execution evidence
passes. Global Phase 10 remains partial without turntable or human visual review, broader
garment/provider evidence, and a mobile profile. It does not authorize Phase 11 dynamic
deformation while C3 remains partial.
