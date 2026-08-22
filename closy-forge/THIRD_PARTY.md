# Third-Party Dependencies

Closy Forge Implementation 01 has no runtime third-party dependencies. Geometry, GLB, package hashing, CLI parsing, and binary binding are implemented with the Python standard library to keep the deterministic foundation small and inspectable.

Development dependencies are pinned in `pyproject.toml`; transitive versions are constrained in `requirements-dev.lock`:

- `pytest==8.3.4`: test runner. Licence: MIT.
- `ruff==0.8.6`: formatting/lint checks. Licence: MIT.
- `mypy==1.14.1`: strict static type checking. Licence: MIT.
- `setuptools==75.8.0`: build backend. Licence: MIT.
- `wheel==0.45.1`: wheel build support. Licence: MIT.
- `colorama==0.4.6`: pytest colour support on Windows. Licence: BSD-3-Clause.
- `iniconfig==2.3.0`: pytest configuration parser. Licence: MIT.
- `packaging==26.3`: pytest packaging/version utility. Licence: Apache-2.0 or BSD-2-Clause.
- `pluggy==1.6.0`: pytest plugin system. Licence: MIT.
- `typing_extensions==4.16.0`: typing backports used by mypy. Licence: PSF-2.0.
- `mypy_extensions==1.1.0`: mypy support package. Licence: MIT.

No GPL, non-commercial, research-only, CUDA, PyTorch, Blender, AI model, API SDK, or external asset dependency is introduced in this milestone.
