from __future__ import annotations

import json
import os
import socket
from pathlib import Path


def main() -> None:
    sensitive = ("TOKEN", "SECRET", "KEY", "SEED", "ORACLE", "TARGET", "GITHUB")
    pinned_base_environment = {"GPG_KEY"}
    network_denied = False
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=0.25)
    except OSError:
        network_denied = True
    root_write_denied = False
    try:
        Path("/canary-write").write_text("forbidden", encoding="utf-8")
    except OSError:
        root_write_denied = True
    report = {
        "status": "pass",
        "nonRoot": os.geteuid() != 0,
        "networkDenied": network_denied,
        "rootWriteDenied": root_write_denied,
        "repositoryAbsent": not Path("/repo").exists() and not Path("/.git").exists(),
        "oracleAbsent": not Path("/oracle").exists(),
        "seedAbsent": not Path("/seed").exists(),
        "dockerSocketAbsent": not Path("/var/run/docker.sock").exists(),
        "hostHomeAbsent": not Path("/root").is_dir() or not os.access("/root", os.R_OK),
        "sensitiveEnvironmentAbsent": not any(
            key not in pinned_base_environment
            and any(marker in key.upper() for marker in sensitive)
            for key in os.environ
        ),
    }
    report["status"] = (
        "pass" if all(value is True for key, value in report.items() if key != "status") else "fail"
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
