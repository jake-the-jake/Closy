# Raster Ingestion V1

BP-49 introduces a deliberately narrow local raster path for project-authored
synthetic fixtures. It is not a real-user capture feature and it does not make
Gate P1 pass.

## Profile

The only enabled profile is `synthetic_fixture_raster_v1`.

The CLI requires:

- a fixture manifest with explicit policy;
- an approved local fixture root;
- allowlisted relative fixture paths;
- expected source byte hashes;
- `not_required_project_fixture` consent and rights classification;
- `allowTrainingUse=false`;
- `allowExternalApis=false`;
- `allowNetwork=false`;
- `containsUserImagery=false`;
- `retentionPolicy=generated_fixture_ephemeral`.

`user_capture`, `production_capture`, unknown profiles, arbitrary paths,
symlinks and hardlinks fail closed.

## Threat Model

The raster path treats image data as potentially sensitive even though the D0
fixtures are project-authored. The implementation guards against:

- identity, face/body and home-interior leakage;
- EXIF location, device and time leakage;
- absolute paths and identifying filenames;
- raw byte fingerprints in portable packages;
- logs, exceptions, test snapshots and CI artifacts;
- decompression bombs and malformed inputs;
- symlink, hardlink and path traversal surprises;
- accidental network or provider upload;
- default training use;
- deletion propagation and cache retention;
- duplicate-source correlation.

Private registry records may contain source byte hashes and normalized decoded
content hashes for reproducible project fixtures. Portable reports exclude raw
bytes, source filenames, absolute paths, EXIF, source byte hashes, decoded
content hashes and durable public source fingerprints.

## Decoder Profile

The D0 decoder uses Python stdlib only.

Supported:

- PNG with magic-byte verification;
- JPEG with magic-byte verification;
- extension/MIME agreement;
- PNG 8-bit grayscale, RGB, grayscale-alpha and RGBA;
- PNG filter reconstruction with CRC checks;
- deterministic JPEG EXIF orientation dimensions;
- metadata stripping policy records;
- bounded file, dimension, pixel-count and decompression limits.

Rejected:

- bad magic or MIME mismatch;
- malformed or truncated PNG/JPEG;
- PNG interlace/APNG;
- unsupported PNG bit depth/color type;
- unsupported ICC/profile behavior;
- excessive byte size, dimensions or decoded pixel count;
- decompression payload mismatch;
- path traversal, symlink and hardlink inputs.

PNG fixtures produce pixel-derived metrics. JPEG fixtures are accepted for
header/orientation coverage in this stdlib-only slice, but JPEG pixel quality is
marked as structural-only until a pinned decoder dependency is introduced and
licensed.

## Outputs

`closy-forge capture ingest-raster-fixture` writes private and portable outputs
to separate roots.

Private registry:

- `private_ingest_record.json`
- `lifecycle_journal.json`
- `normalization_record.json`
- `raster_quality.json`

Portable output:

- `source_summary.json`
- `privacy_report.json`

`closy-forge capture delete-raster-fixture` removes Forge-managed private JSON
records and writes a non-recoverable tombstone. It never deletes a user-owned
original outside the Forge-managed registry. Repeated deletion is idempotent.

## Current Limitations

- No private user captures are accepted.
- No provider upload exists.
- No training use is permitted.
- No raw source image is copied into a `.closygarment` package.
- JPEG pixel decoding is intentionally absent in this dependency-free slice.
- BP-50 masks and garment visibility confidence remain the next dependency-ready
  visual-understanding step.
