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

- `self_collision_not_run`: expected warning for the first deterministic CPU reference solver.
- `cloth_settle_not_run`: warning for legacy/unfinished packages that do not run settle.
- `cloth_settle_not_converged`: package claims settle availability but diagnostics did not converge.
- `cloth_settle_body_penetration_too_high`: settled state penetrates the avatar beyond the reference threshold.
- `cloth_settle_seam_residual_too_high`: settled seam residual exceeds the reference threshold.
- `cloth_settle_material_contradiction`: material preset and manifest disagree about whether settle ran.
- `settled_state_content_hash_mismatch`: persisted settled state does not match the simulation mesh manifest.
- `capture_provider_policy_violation`: synthetic fixture capture permits external API or training use.
- `capture_record_hash_mismatch`: capture record content changed without updating its canonical payload hash.
- `capture_quality_source_hash_mismatch`: capture quality report points at the wrong source hash.
- `capture_quality_not_pass`: capture quality report does not pass the current fixture gate.
- `capture_quality_below_threshold`: capture quality score is below its declared threshold.
- `visual_observation_hash_mismatch`: visual mask/landmark observations changed without updating their payload hash.
- `required_tshirt_visual_landmark_missing`: visual observations do not include a required T-shirt landmark.
- `visual_mask_point_out_of_range`: synthetic mask polygon contains a point outside normalized image space.
- `correction_record_hash_mismatch`: editable correction record content changed without updating its payload hash.
- `correction_policy_violation`: correction record permits external API or training use.
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
