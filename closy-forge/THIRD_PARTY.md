# Third-Party Dependencies

Closy Forge Implementation 01 has no runtime third-party dependencies. Geometry, GLB, package hashing, CLI parsing, and binary binding are implemented with the Python standard library to keep the deterministic foundation small and inspectable.

Development dependencies are pinned in `pyproject.toml`:

- `pytest==8.3.4`: test runner. Licence: MIT.
- `ruff==0.8.6`: formatting/lint checks. Licence: MIT.
- `mypy==1.14.1`: strict static type checking. Licence: MIT.
- `setuptools==75.8.0`: build backend. Licence: MIT.
- `wheel==0.45.1`: wheel build support. Licence: MIT.

No GPL, non-commercial, research-only, CUDA, PyTorch, Blender, AI model, API SDK, or external asset dependency is introduced in this milestone.
