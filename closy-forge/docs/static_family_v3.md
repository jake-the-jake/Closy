# Static Family V3 Sidecar

This opt-in Windows/CPU static pass consumes the **completed A evaluation**, selecting
`build1/<family>/nominal` for the nine registered families. It does not compile or settle
garments, run the legacy `integrate_static` campaign, modify A, change ZeroOne, or publish
over historical evidence. Parent-owned conventional runtime, outfits, collision and demo
work remain separate. Static success does not establish seam acceptance, physics,
capture estimation, integration-gate dynamic Z2, mobile performance or product readiness.

## CLI

From `E:/apps/Closy-all-family-layer-integration-v1/closy-forge`, after A has terminated:

```powershell
$env:PYTHONPATH = 'src'
py -3.11 scripts/evaluate_static_family_v3.py `
  --evaluation-root .tmp/family-final-v2 `
  --output E:/apps/closy-static-v3-03 `
  --reuse-published-pr66
```

Use a **short absolute output root** on Windows. The completed run is already retained at
`E:/apps/closy-static-v3-02`; `-03` above is only a fresh-path example for a future authorized
run, not an instruction to rerun completed evidence. A deep worktree-relative output caused
page-pack staging path-length failures in the retained first attempt (see receipts below).

The output directory must be new and disjoint from A. The reuse option is explicit owner
authorization to capture a NEW read-only registry receipt, not to reconstruct the missing
historical build record. Alternatively pass `--trusted-build-record <existing-json-path>`
(or `CLOSY_ZEROONE_TRUSTED_BUILD_RECORD`) and omit `--reuse-published-pr66`. With neither,
the original resolver retains nine `not_run` dependency rows; no adapter or processor is run.
Exit codes: **0** all nine static audits passed; **1** execution/audit/source-freshness failure;
**2** optional dependency not run. There are no automatic retries, resume reruns, sealed
campaigns, or generated test-pass receipts. Checkpoints preserve every attempted family.

Defaults: executable `E:/apps/ZeroOne-pr4-build/Release/ZeroOneProcess.exe`; read-only source
`E:/apps/ZeroOne-pr4-static`. Override with `--executable` / `--zeroone-source`, but the
expected hashes, source commit and tree remain pinned.

## Reuse Trust

The existing trust contract accepts `owner_controlled_registry`; no validator or version
guard is modified. The new receipt is derived only after all these read checks pass:

- Frozen registry bytes come from Git commit
  `930b3da556c96e9ded52b6ee8df5620d4903c280`, path
  `closy-forge/docs/evidence/static_zeroone_runtime_v2/result.json`.
- Registry byte SHA256 is
  `d7913d3cd59139b6aae19fa797b1d2a942467e31f292abc7567d795fd2e2851f`.
- Current executable SHA256 is exactly
  `38adb7797344b9fcbbe814ed0bb47c0b23b40577341ecda92d911410ad8ba1a6`.
- Current source is clean at `9cbae4a8e6ef2e61c1839ecbdf8a462aaa560027`, tree
  `6e058711449fdd98c41c82d05294339b3f21fc16`, before and after the capture.
- Actual `version-json` exits zero and its **whole JSON object** equals the published
  `source.zeroOneVersion`. The unchanged trusted-record and version validators then pass.

The attestation kind is `read_only_reuse_of_published_PR66_hash`, with
`buildReexecuted=false` and `originalTrustRecordNotRecovered=true`. Its `buildId` explicitly
names a reuse capture, not an invented original build. Historical record SHA256
`aea342d86a550a28a5e88c90ffb2c2595836c36568eef3a7c8eed5491cdde375` is retained as a missing
historical reference; the new record has its **own different hash**. `commandTemplate`
lists only actual local hash/Git/version checks. `networkAllowed=false` applies only to
this capture's local-check policy, not the historical build; network isolation is not claimed.
The normal `resolve_zeroone_tool` is called with the new record and pinned identities before
any processing. Failed reuse checks retain their attempt receipt and nine `not_run` rows.

## Adapter And Audit

`create_family_adapter(source, destination)` first checks A's non-self-referential identity,
bounded inventory, byte hashes and read-only `validate_family` result. It pins bytes before
copying, rechecks A after copying, and never writes into A. The fresh copy-view uses
`adapterVersion=closy.zeroone.family_adapter.v1` and its own `adapterIdentity`; integer
`schemaVersion=1` describes this new envelope, **not** a legacy `packageVersion` claim.

The original manifest is retained byte-for-byte at `source/family_manifest.json`, with
its original profile and package identity. Original inventory assets retain exactly their
bytes and paths. Added coordinates, render topology hash and canonical role paths adapt
only the envelope to `closy.zeroone.static-request.v1`. The unchanged
`build_zeroone_request` constructs the frozen request. Six authority roles have distinct
paths; `appearance/material.json` records the actual fallback GLB material table, not the
simulation material and not capture-estimated appearance. The source record explicitly
points back to the original family manifest and manual-input authority.

`verify_family_adapter(package)` rechecks the envelope, original manifest identity, asset
lineage and appearance provenance. `audit_static_family(derivative_root,
adapter_package=...)` retains V2's actual Z4/Z5/Z6/Z8 inventory, hierarchy, LOD, page range,
checksum and semantic evidence, but replaces counts-only geometry acceptance:

- Source and leaf triangles use emitted **float32** POSITION.xyz and TEXCOORD_0.uv values.
  Cyclic vertex rotation is equivalent; reversed winding is not. Multiplicity is preserved.
- Signed per-triangle I32 materials are reread from bounded leaf payloads after the existing
  page decoder. Its collapsed `Mesh.material_id` label is not coverage evidence.
- Tolerance is absolute `1e-6` metres per position component and `1e-6` per UV component.
  Unique oriented-triangle correspondence is required; tolerance or cross-panel ambiguities
  fail closed. Exact float32 multiset equality is reported separately from tolerance matching.
- Source panel IDs must match the semantic graph. Panel correspondence is **derived** from
  matching source triangles; embedded panel IDs are never claimed. The decoder's fabricated
  `panel.front` placeholder is ignored. Dense material index/name mapping is checked too.
- Min/max/size bounds must all differ by at most `1e-6` metres, including unused source
  vertices. This predicate is mandatory for Z4/Z8 pass, even when triangle multisets match.

Bounded copy/audit scope: at most 64 MiB per asset, 256 MiB source/copy inventory, 256
inventory entries, existing decoder count/range limits, and five million candidate
triangle comparisons. Exceeding bounds fails; it is not a claim of arbitrary-size support.
Only the conservative untransformed/non-instanced GLB subset is audited. Z3/Z7 remain
`not_run`: this processor has no required classification/bake payloads. Stage counts describe
completed independent audits, not an inferred CPU stage timeline. Command receipts and
`processorCookExecuted` separately record actual processor execution; a thrown incomplete
audit is labeled `failed_before_complete_stage_audit`, not silently called a pass.

## APIs And Receipts

The script exposes `run(evaluation_root, output, *, executable, zeroone_source,
trusted_build_record=None, reuse_published_pr66=False, forge_root=None)` and read-only
`inspect_pr66_reuse(forge, zeroone, executable)` (returns an in-memory new record/capture).
The audit exposes pure `compare_triangle_coverage(source, decoded, ...)` and
`read_leaf_materials(page_root, decoded.audit)` for bounded decoded payload inspection.

Output-root receipts are `protocol.json`, `source_receipt.json`, `tool_receipt.json`,
`checkpoint.json`, `result.json`, and `receipt_manifest.json` (last, hashes compact receipts).
With successful opt-in reuse: `read_only_reuse_record.json`, `read_only_reuse_capture.json`.
Failed opt-in reuse instead retains `read_only_reuse_attempt.json`.
Per family: `adapter_receipt.json`, `request.json`, command stdout/stderr and exit receipts,
`static_stage_audit.json`, `adapter/`, and `processor/current/` derivative bytes. Large
assets remain only in those work directories; compact receipts do not duplicate GLBs or packs.

The script's current-source receipt names eleven selected adapter/audit/request/decoder,
compiler and test files. This is **not a complete transitive source freeze** and is not A's
original start inventory. It rechecks only those selected files, the saved A result/index/
checkpoint, and each processed source package; unrelated B/C additions do not invalidate A.
The parent's publication owns the stronger A reachable-closure receipt and original inventory.

## Focused Verification

Pure tests use tiny inert source/derivative fixtures and mocked process outcomes, not a
nine-family cook or build. They cover changed triangle/winding/UV/material, material-order
loss, duplicate counts, ambiguous panels, float32 identity, mandatory bounds, A mutation,
source lineage, missing trust, retained failures, and truthful reuse/mismatch rejection.

```powershell
$env:PYTHONPATH = 'src'
py -3.11 -m pytest tests/unit/test_static_family_v3.py
py -3.12 -m pytest tests/unit/test_static_family_v3.py
py -3.12 -m ruff check src/closy_forge/zeroone/family_adapter_v1.py src/closy_forge/zeroone/static_stage_audit_v3.py scripts/evaluate_static_family_v3.py tests/unit/test_static_family_v3.py
py -3.12 -m ruff format --check src/closy_forge/zeroone/family_adapter_v1.py src/closy_forge/zeroone/static_stage_audit_v3.py scripts/evaluate_static_family_v3.py tests/unit/test_static_family_v3.py
$env:MYPYPATH = 'src'
py -3.12 -m mypy --follow-imports=silent src/closy_forge/zeroone/family_adapter_v1.py src/closy_forge/zeroone/static_stage_audit_v3.py scripts/evaluate_static_family_v3.py tests/unit/test_static_family_v3.py
```

During sidecar implementation, read-only Git/hash/version inspection matched the identities
above. The parent subsequently executed the following two serial runs. This documentation
update inspected their saved receipts only; no static code changes or processor reruns were made.

## Executed Receipts

Final output: `E:/apps/closy-static-v3-02`, parent process exit **0**. Saved result reports
**9/9 passed**, with **9 passes each for Z4, Z5, Z6 and Z8**. Z3 and Z7 each remain
**9 not_run**, not completed stages. Both `selectedCurrentFilesUnchanged` and
`sourceEvaluationUnchanged` are true. These are the saved A nominal family adapter inputs;
the run does not claim static processing of the later B local-frame binding package format.

- Result: `E:/apps/closy-static-v3-02/result.json`, SHA256
  `f830688f89a9c60b01604d4ad32deb587350297d1fefd49357cfeccadf2ff032`.
- Compact receipt manifest: `E:/apps/closy-static-v3-02/receipt_manifest.json`, 115 entries,
  SHA256 `81b44b90bd643f6d6a66defb2fb1a8917dfe85091016cbcfef4007139c567779`.
- New reuse record: `E:/apps/closy-static-v3-02/read_only_reuse_record.json`, SHA256
  `1873a613241647353b0b572d52a93015be8e1c08be6c121de90ba8a445ac7f28`.
  `matchesHistoricalTrustedRecordHash=false` is intentional: the original record was not
  recovered, and no new build was executed. The executable still matches the frozen PR66 hash.
- Per-family stage receipts are `E:/apps/closy-static-v3-02/<family>/static_stage_audit.json`;
  inspect/cook/validate exit receipts and logs remain beside each adapter.

The initial deep-root attempt remains intact at
`E:/apps/Closy-all-family-layer-integration-v1/closy-forge/.tmp/static-family-v3-01`.
Its result records **0 passed, 9 failed**; inspect succeeded but every cook exited **20** with
`E_STATIC_CACHE_PUBLICATION: cannot create page-pack staging directory`. Result SHA256:
`80a9894676d2de119371c83885f35dd766d95b307854d6ed5449711d13dc1fe4`.
The parent isolated the Windows path-length issue by switching to the short root; the
processor, Closy code, and A source packages were unchanged. The failed run is not replaced
or converted to success. No ZeroOne source change, build reexecution, dynamic readiness,
cloth/seam qualification, capture estimation or mobile-device claim follows from the final pass.
