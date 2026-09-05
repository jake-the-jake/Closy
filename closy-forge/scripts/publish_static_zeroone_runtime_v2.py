from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.zeroone.static_runtime_v2_publication import publish_static_runtime_v2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish independently checked static runtime v2 evidence."
    )
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--transition-commit", required=True)
    args = parser.parse_args()
    manifest = publish_static_runtime_v2(args.repository.resolve(), args.transition_commit)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
