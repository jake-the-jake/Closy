# Unit U Final Strategy-3 Confirmation v2

## Literal Outcome

`dependency_blocked_before_official_seed_v2`

The final strategy was reserved and locked as
`PHY1-V5-S3-SEAM-SEQUENCE-CONFORMING-REMESH-V2`. Two bounded public conformance cycles were
used: the first failed implementation conformance and the corrected second cycle passed all
`8/8` fixtures through the production assembly path. The exact generic preflight run
`33630652037` passed its Ubuntu verifier, Windows verifier, container build, and networkless
non-root canary with image
`sha256:07f54a27f9bce38c5be7c6e26ac906eee2cbaa19c83b68a2354064c80f695247`.

## Pre-seed Block

Official run `33630862367` targeted exact lock head `d76916461d3e96b037fbc31b646319effef7a264`. Both portable
decision-verifier jobs passed, and the public proof again passed `8/8`. The pinned-container
preflight then failed the lock self-consistency test before image creation because four inherited
files had been hashed from a Windows `core.autocrlf=true` worktree. Their committed repository
blobs are LF, so the Linux authority checkout correctly produced different byte hashes:

- `src/closy_forge/recovery_foundation_v2/topology_holdout.py`: locked CRLF `372ecba0d34527411d5e184767e399a9225dc49fa3ac21997e2a450e80e09692`; repository LF `3f595f60c5da54df3f9da901738de0000177de251f81e7994a85984823308f6e`.
- `src/closy_forge/recovery_foundation_v2/topology_holdout_oracle.py`: locked CRLF `c0cf79f42ea70ec3ac54ba426a726d65247e57d00759d615797ccd861e573878`; repository LF `ffc96bde5658e59c16373c7cca2f044c8a64db38476942659449fd51e47e88a8`.
- `src/closy_forge/simulation/reference_cloth_solver.py`: locked CRLF `cfa7ea16dfe952e66adce856cd7cb5700cc0b1074b882cddc76a2f480d38edb9`; repository LF `928069f98f049e0aace9625473c77a93caebc0bda9a7b0afa38b5587086b4f41`.
- `src/closy_forge/simulation/self_collision.py`: locked CRLF `92980ead1dcfc4329a1ef6c6b72847923ffaeae556ee873092d3a9a7fa8f9187`; repository LF `0ddbcb2ff69b878030da91ef9bc9502a1efd5c74da0d8451a52ee3e8b477f5a9`.

The authority job was skipped. No official seed, nonce, commitment, fixture, oracle value,
strategy execution, or authority artifact existed. The untouched confirmation attempt therefore
was not consumed. This is a locked-path portability/dependency block, not evidence that Strategy
3 passed or failed its scientific gates.

The prompt forbids relocking after the final lock. No locked byte was changed and the authority
was not rerun. GitHub Actions workflow `348397321` was disabled in repository
control as `disabled_manually`, sealing dispatch without modifying its locked file bytes.

## Consequences

- Strategy admission: `false`; confirmation was `not_run`.
- Unit V: ineligible because literal Unit-U admission is absent.
- Units W and X: transitively ineligible.
- Topology-strategy budget: `0` remaining; the final reservation/lock consumed the third slot.
- Canonical-candidate budget: `1` remaining; no canonical T-shirt transformation occurred.
- Seam-model budget: `0` remaining.
- Runtime v1 package and conventional fallback remain unchanged.

The locked Strategy-3 implementation and its public `8/8` conformance are preserved as
non-qualifying engineering evidence. A future attempt requires explicit user-authorised successor
methodology and a new portable repository-blob-based lock; this prompt authorises neither a relock
nor another official authority event.
