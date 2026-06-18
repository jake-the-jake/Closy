# Avatar Texture Slots

Optional shared texture location for future avatar assets.

Preferred maps:

- `*_baseColor` or `*_albedo`
- `*_normal`
- `*_roughness`
- `*_metallic`
- `*_ao`

Mobile guidance:

- Prefer embedded GLB textures for the first production pass.
- Keep textures power-of-two and 1k by default, 2k only for hero assets.
- Avoid unsupported shader features such as transmission/dispersion in Expo GL.
