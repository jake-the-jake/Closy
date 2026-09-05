# Outfit Saved-Evidence Archive

The final saved-evidence publisher produces hundreds of detailed contact/transport
receipts. Its complete expanded output is distributed losslessly in `receipts.zip`
instead of repeatedly committing hundreds of large witness files. Summaries, the
Phase 0-14 view and three actual-geometry images remain directly readable.

This is an explicit distribution envelope, not a changed garment/runtime format.
`archive_envelope.json` inventories the ZIP and visible copies. Original manifests
under `expanded-metadata/` describe **archive members**, not the outer directory.
The ZIP contains those original manifests and every original published payload byte.
Portable projection notices and raw-versus-published hashes are retained unchanged.
The existing evidence scanner passed on all expanded text before compression; the
scanner's inability to inspect ZIP members is not treated as validation.

The package is built twice using sorted entries, fixed 1980-01-01 timestamps, regular
0644 Unix attributes and DEFLATE level 9. Its envelope records Python/zlib versions.
Both archives must be byte-identical. Every entry is then bounded, decoded and checked
against the original manifest's SHA-256 and size. Visible copies match archived bytes.
The preflight reduced 526 files / 46134970 expanded bytes to a 7274466-byte archive;
final source/test inventories add a small explicitly inventoried increment. The full
local suite's exit receipt is attached to the final PR handoff after it completes;
the archived prepublication snapshot explicitly marks that process as running.

Final distribution: 531 members, 46353259 expanded bytes, 7378811 ZIP bytes; archive
SHA-256 `8862ddbffb200279fdcf5a118aed80fb7e5a1f7d561f981c687c8f3fd3571caf`.
The exact verification command below was executed successfully against the committed
directory layout with a fresh local extraction root. Raw test-node parameter examples
remain local; their exact hashes and all shard/source inventories are published.

The visible HTML copy retains its original CRLF bytes. A file-scoped Git whitespace
attribute recognizes CR as that artifact's line ending; its strict byte hash is not
normalized or weakened. The linked demo and outfit audit JSON are exact visible copies
too, so the inspection page does not contain dangling audit links.

No GLB, ZeroOne binary or physical-user data is included. Actual generated conventional
models remain in the tested local demo/output roots. The archive preserves evidence,
not a standalone replacement for those input packages. GitHub cannot inline-diff ZIP
witnesses; the visible summary explicitly retains all failed fit counts.

## Verify And Expand

Run from the Forge directory. Use a fresh output beneath that directory. Trust the
reviewed Git commit/envelope before use: a self-declared digest alone is not authenticity.
Do not run Python with `-O`, which disables the verification assertions below.

```powershell
$verify = @'
import hashlib, json, sys, zipfile
from pathlib import Path, PurePosixPath
bundle, output = map(Path, sys.argv[1:3])
env = json.loads((bundle/"archive_envelope.json").read_text())
canonical = lambda v: json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()+b"\n"
declared = env.pop("envelopeDigest")
assert hashlib.sha256(canonical(env)).hexdigest() == declared
assert env["version"] == "closy.outfit.saved_evidence.archive.v1"
assert not output.exists() and output.resolve().is_relative_to(Path.cwd().resolve())
archive = bundle/"receipts.zip"
assert archive.stat().st_size == env["archive"]["bytes"] <= 80*1024*1024
assert hashlib.sha256(archive.read_bytes()).hexdigest() == env["archive"]["sha256"]
with zipfile.ZipFile(archive) as z:
    infos=z.infolist()
    names=[i.filename for i in infos]
    assert len(names)==len(set(n.casefold() for n in names))==env["archive"]["members"]<=1024
    assert sum(i.file_size for i in infos)==env["archive"]["expandedBytes"]<=80*1024*1024
    assert z.getinfo("publication_manifest.json").file_size<=1024*1024
    raw=z.read("publication_manifest.json")
    assert hashlib.sha256(raw).hexdigest()==env["expandedManifestSha256"]
    pub=json.loads(raw)
    assert pub["publicationDigest"]==env["expandedPublicationDigest"]
    expected={r["path"]:(r["bytes"],r["sha256"]) for r in pub["inventory"]}
    expected["publication_manifest.json"]=(len(raw),hashlib.sha256(raw).hexdigest())
    assert set(names)==set(expected)
    for info in infos:
        name=info.filename
        p=PurePosixPath(name)
        assert not p.is_absolute() and all(v not in ("",".","..") for v in p.parts)
        assert "\\" not in name and ":" not in name and not info.is_dir()
        assert not info.flag_bits&1 and (info.external_attr>>16)&0o170000==0o100000
        assert info.file_size==expected[name][0]<=16*1024*1024
        with z.open(info) as f: data=f.read(16*1024*1024+1)
        assert (len(data),hashlib.sha256(data).hexdigest())==expected[name]
        dest=output.joinpath(*p.parts)
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open("xb") as f: f.write(data)
    for row in env["visibleCopies"]:
        data=(bundle/row["path"]).read_bytes()
        assert (len(data),hashlib.sha256(data).hexdigest())==(row["bytes"],row["sha256"])
        assert data==z.read(row["archiveMember"])
print("PASS: exact bounded archive extraction and visible-copy hashes")
'@
py -3.11 -c $verify docs/evidence/outfit_layer_runtime_v1 .tmp/outfit-evidence-expanded
```

The verification rejects unsafe/duplicate paths, links, encrypted entries, extra or
missing members, wrong hashes/sizes and bounded-expansion violations. It does not
execute archive content. Keep a failed partial extraction as untrusted; choose a fresh
output for a diagnosed retry rather than overwriting an earlier receipt.

Packaging/extraction are separately verified publication operations performed after
the runtime evaluations. They do not rerun geometry, contacts or cloth, and are not
presented as having been covered by an earlier cumulative test invocation.
