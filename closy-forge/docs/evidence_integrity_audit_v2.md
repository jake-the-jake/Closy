# Evidence Integrity Audit v2

The blocking evidence scan covers generated status, PR graph, execution-budget, active-resume,
ZeroOne integration documentation, and every committed file under `docs/evidence/`. The supplied
canonical master blueprint is intentionally excluded because it is source authority, not generated
output.

## Blocking Result

- Windows absolute paths: none.
- POSIX home paths: none.
- URI credentials: none.
- common token formats: none.
- private capture registry identifiers: none.
- unexpected subject, participant, or customer identities: none.

## Separate Legacy Inventory

The wider repository scan finds deliberate hostile examples only in security tests, including a
synthetic Windows home path, a synthetic POSIX home path, fake URI credentials, and fake token and
private-capture identifiers. These are test inputs, not evidence or publication records. Ordinary
public GitHub URLs in the PR ledger are reviewed public metadata and do not match the boundary-aware
credential or absolute-path detectors.

No wildcard path allowlist is used. No private fixture path or registry identity is allowlisted.
