# Simple-Dress D0 Vertical Slice

The Phase 8 simple-dress fixture exercises the shared Closy garment pipeline with a literal
one-piece family rather than treating a top and skirt as unrelated objects.

- Four panels: front/back bodice and front/back skirt.
- Eight seams: paired shoulder and bodice-side seams, front/back waist joins, and skirt-side seams.
- Four semantic openings: neck, hem, left armhole and right armhole.
- The waist is sewn and is not represented as an opening.
- Bounded 25-candidate fitting adjusts half-waist width and skirt length.
- Four material presets plus deterministic armhole-stress motion execute through the reference CPU
  cloth solver and authoritative dense binding.
- Front/back synthetic source views combine the bodice and skirt at their authored world heights,
  then decoded source-versus-render fidelity is measured independently.
- A conventional dense GLB and a direct-simulation fallback GLB are both persisted.

The canonical fixture contains 193 simulation vertices, 189 simulation triangles, 1,134 dense
vertices, 756 dense triangles and 1,134 binding records. Its package digest is
`e8b1a3c00d9276c9d95ee2525bf3e24c88a84ee4ab03a5f5472e73175663b00a`.

This is a project-authored synthetic CPU fixture, not private-user fitting, measured real-fabric
calibration, learned inference, production GPU cloth or mobile performance evidence. Shirts with
openings/buttons remain next and Phase 8 remains globally partial.
