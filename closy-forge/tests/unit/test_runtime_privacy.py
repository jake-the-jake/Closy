from __future__ import annotations

import json
from pathlib import Path

from closy_forge.package_io.managed_output import (
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.runtime_delivery import (
    PrivateDerivative,
    create_portable_source_link,
    register_private_source,
    withdraw_private_source,
)


def _publish_derivative(path: Path, purpose: str, payload: bytes) -> None:
    staging = create_managed_staging(path, allowed_root=path.parent, purpose=purpose)
    (staging / "artifact.bin").write_bytes(payload)
    publish_managed_staging(
        staging,
        path,
        allowed_root=path.parent,
        purpose=purpose,
        force=False,
    )


def test_private_registry_keeps_raw_mapping_private_and_withdrawal_is_selective(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "private-source-registry.json"
    private_derivative = tmp_path / "private-derived"
    authorized_artifact = tmp_path / "authorized-garment"
    _publish_derivative(private_derivative, "private-derived", b"identity-linked")
    _publish_derivative(authorized_artifact, "authorized-garment", b"non-identifying")

    opaque = register_private_source(
        registry,
        source_bytes=b"private capture bytes",
        hmac_key=b"k" * 32,
        scope="closy-private-capture-v1",
        consent_scope="garment-fit-derived-artifact",
        retention_policy="until-withdrawal",
        deletion_policy="delete-identity-linked-derivatives",
        derivation_policy="allow-non-identifying-garment-output",
        derivatives=(
            PrivateDerivative(private_derivative, "private-derived"),
            PrivateDerivative(
                authorized_artifact,
                "authorized-garment",
                authorized_non_identifying=True,
            ),
        ),
    )
    portable = create_portable_source_link(registry, opaque)
    registry_payload = json.loads(registry.read_text(encoding="utf-8"))
    raw_hash = registry_payload["records"][opaque]["rawSourceSha256"]

    assert raw_hash not in json.dumps(portable, sort_keys=True)
    assert portable["opaqueId"] == opaque
    assert portable["withdrawalStatus"] == "active"

    receipt = withdraw_private_source(registry, opaque)

    assert receipt["rawMappingRemoved"] is True
    assert not private_derivative.exists()
    assert authorized_artifact.is_dir()
    withdrawn = json.loads(registry.read_text(encoding="utf-8"))
    assert opaque not in withdrawn["records"]
    assert raw_hash not in registry.read_text(encoding="utf-8")
    assert withdrawn["withdrawals"][opaque]["withdrawalStatus"] == "withdrawn"
