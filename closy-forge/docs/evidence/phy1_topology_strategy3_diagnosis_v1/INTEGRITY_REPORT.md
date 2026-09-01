# Unit O Cross-Minor Integrity Attestation

The pre-execution lock and raw bounded-diagnosis evidence remain unchanged. Both raw revisions
passed `7/8` development fixtures and admitted no strategy class, but exact-head Forge run
`33559874476` could not regenerate those committed bytes on its Python/platform matrix.

A local Python 3.11 reproduction identified three `totalAbsoluteImpulseNewtonSeconds`
accumulations differing by one binary64 ULP; Linux regeneration contains additional
platform-dependent numeric drift. The resulting changes alter deterministic-repeat fixture and
revision digests. No acceptance threshold failed or changed, but the preregistered exact
cross-minor evidence promise was not met. No numeric drift is accepted or normalised by the
attestation verifier.

The effective Unit O outcome is therefore `diagnosis_integrity_error`. The raw execution was not
patched or replayed. No Unit P seed or instance exists, no candidate was created, and neither the
candidate attempt nor final topology strategy was consumed. Units P, Q, and R remain ineligible;
runtime v1 and its conventional fallback remain selected.
