from __future__ import annotations

from pathlib import Path

from closy_forge.d0_v4_engineering.forensic import (
    validate_v3_forensic_erratum,
    write_v3_forensic_erratum,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output = root / "docs/evidence/d0_v4_engineering/v3_forensics"
    report = write_v3_forensic_erratum(root, output)
    issues = validate_v3_forensic_erratum(report)
    if issues:
        raise SystemExit(";".join(issues))
    print(f"wrote {output} ({report['erratumDigest']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
