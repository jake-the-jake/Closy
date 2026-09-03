# D0 v4 observable synthetic engineering corpus v5

This v5 corpus supersedes v4 for final engineering validation while retaining
all earlier corpora and failed results. It preserves the full compiler-safe
parameter domains and the non-clipping capture envelope. The 2D capture polygon
now orders the sleeve interior strictly between the cuff and armhole and measures
armhole depth below the shoulder line. Valid combinations therefore no longer
produce a self-crossing or depth-reordered silhouette that hides armhole depth.

The corpus is CC0-1.0 project-authored development evidence with 512 training,
128 validation, and 128 untouched public-test identities under new
domain-separated seeds. It is not a qualification cohort. Public-test target
access remains fail-closed until the sole authorized execution.

`manifest.json` and `captures.zip` contain only training and validation data.
`public_test.manifest.json` and `public_test.captures.zip` are a separate guarded
one-shot inventory, so development loaders cannot deserialize public-test targets.
