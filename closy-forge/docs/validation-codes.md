# Validation Codes

Validation issues use stable fields:

- `code`
- `severity`: `info`, `warning`, `error`, or `fatal`
- `path`
- `entity_id`
- `message`
- `remediation`

The CLI exits with:

- `0`: success;
- `2`: command/argument error;
- `3`: package validation failure;
- `4`: deterministic build failure;
- `5`: unsafe path or integrity failure.

Representative current codes:

- `cloth_settle_not_run`: expected warning for Implementation 01.
- `unsupported_schema_version`: unsupported `schemaVersion`.
- `required_file_missing`: required package file absent.
- `unsafe_package_path`: inventory path escapes the package contract.
- `escaping_symlink`: symlink resolves outside package root.
- `file_hash_mismatch`: declared SHA-256 does not match disk content.
- `duplicate_panel_id`: pattern panel IDs are not unique.
- `dangling_seam_reference`: seam references an unknown panel or edge.
- `panel_boundary_self_intersects`: sampled panel boundary self-intersects.
- `nonfinite_numeric_value`: NaN or Infinity is present.
- `invalid_constraint_vertex`: seam constraint references an invalid vertex.
- `glb_parse_failed`: GLB cannot be parsed as GLB 2.0.
- `binding_invalid`: binding header/layout is malformed.
- `binding_triangle_out_of_range`: binding record references an invalid simulation triangle.
- `binding_sim_topology_hash_mismatch`: binding source hash does not match manifest.
- `false_zeroone_capability`: package claims unavailable ZeroOne output.
