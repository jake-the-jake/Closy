# Phase 9 Structured-Pattern Foundation D0

> Historical v1 baseline: this document describes the original non-learned 24-sample retrieval
> fixture. The implemented learned synthetic D0 successor is documented in
> `pattern-inference-learned-synthetic-d0.md`; v1 remains reproducible as the rollback/audit anchor.

This phase implements only the runnable, non-learned foundation for future structured-pattern
inference. It is restricted to human-avatar garments and uses project-authored synthetic records.

## Executed Foundation

- versioned `closy.structured_pattern_grammar.d0.v1` with eight garment template productions;
- deterministic template retrieval/ranking from category, panel count and opening count;
- 24 synthetic samples covering eight families and multiple panel counts;
- immutable 8/8/8 train/validation/test split with no sample overlap;
- project-authored human-correction record contract;
- benchmark harness that independently reruns ranking for all 24 samples;
- bundle-integrity hash and fail-closed recomputation for split, benchmark and evidence tier;
- six generated JSON schemas and deterministic six-document writer.

The deterministic baseline selects all 24 authored targets. This is fixture correctness, not learned
accuracy or evidence of generalisation.

## Limits

No model was trained, no weights exist, no private or external dataset was used, and no learned
accuracy/generalisation claim is made. The synthetic split is a contract fixture, not a statistically
representative fashion dataset. Phase 9 remains partial until authorised data, training, held-out
evaluation and model governance exist.
