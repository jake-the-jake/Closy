# D0 identity-disjoint T-shirt confirmation v2 lock

Unit M is locked on Unit L publication head
`a72f45955abbe65ce14b7142668447d0477db71c`. This lock contains no fresh v2 evaluator
identity, target, target hash, nonce, seed, prediction, or result.

The protocol preserves 16 evaluator identities and 64 fixed-route predictions. Three routes own
48 compile/3D slots plus 16 non-reassignable primary repeats. The first eight ordinals own 24
appearance slots plus eight non-reassignable primary repeats. Failures remain in every denominator.
The fixed primary route is `deterministic_masks_landmarks`; no per-identity route mosaic is allowed.

Development proof uses only generic fixtures and the already-revealed Unit G v1 cohort. It now
dispatches all 48 compile slots and all 24 appearance slots; three contaminated-v1 compiles fail
literally rather than being removed. This proves harness behavior only and closes no Research
Prototype row.

The official authority is a one-shot pull-request workflow at the exact implementation-lock head.
One replacement workflow run is permitted only after a recorded pre-draw infrastructure failure
with no seed, commitment, prediction, reveal, or published artifact. Authority run `33530331133`
failed in the platform-sensitive lock-regeneration check before the authority script executed;
job `99931572124` published zero artifacts. Replacement run `33531607760`, job `99935863093`,
also stopped before authority execution because inherited Unit-L files were CRLF in the Windows
lock worktree but LF in Git and Ubuntu; it likewise published zero artifacts. The lock now hashes
UTF-8 source text with canonical LF and a final newline, validates its complete implementation
inventory directly, and requires every prior authority run to match this committed pre-draw ledger.

Official immutable authority run `33532344652` (job `99938286152`) then generated the seed,
16 accepted identities, private target/source bytes, and cohort commitments before its Docker
negative control failed to write `/outputs/probe.json`. No prediction or target reveal occurred,
and the skipped upload left no recoverable artifact. Because accepted source bytes and commitments
already existed, the attempt is sealed as `attempted_integrity_error`; all four scoped D0 rows fail
their retained denominators and no qualification retry is permitted. The event does not claim
cryptographic target secrecy.

No evaluator, model, route, threshold, metric, or lock byte changed after authority began. The
workflow is now verification-only and cannot dispatch another seed, cohort, prediction, or evaluator.
