FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 PYTHONPATH=/app/src
WORKDIR /app
COPY src/closy_forge/__init__.py /app/src/closy_forge/__init__.py
COPY src/closy_forge/final_strategy3_v2 /app/src/closy_forge/final_strategy3_v2
COPY src/closy_forge/contracts /app/src/closy_forge/contracts
COPY src/closy_forge/geometry /app/src/closy_forge/geometry
COPY src/closy_forge/package_io /app/src/closy_forge/package_io
COPY src/closy_forge/simulation /app/src/closy_forge/simulation
COPY docker/strategy3_blob_authority_v3/runner.py /app/runner.py
COPY docker/strategy3_blob_authority_v3/isolation_canary.py /app/isolation_canary.py
COPY docker/strategy3_blob_authority_v3/entrypoint.sh /app/entrypoint.sh
RUN chmod 0555 /app/runner.py /app/isolation_canary.py /app/entrypoint.sh \
    && find /app -xdev -type f -exec sha256sum {} \; > /app/image-file-sbom.sha256
USER 65532:65532
ENTRYPOINT ["/app/entrypoint.sh"]
