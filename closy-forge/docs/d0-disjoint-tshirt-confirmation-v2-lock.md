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
It creates a random 256-bit seed in the trusted job, generates truth and source observations
together, keeps targets unmounted while all 64 predictions run in Docker with a read-only allowlist
and `--network none`, freezes predictions, then reveals and evaluates the existing targets. The
event does not claim cryptographic target secrecy.

The canonical outcome will be imported additively after the authority artifact is complete. No
evaluator, model, route, threshold, metric, or lock byte may change after that authority begins.
