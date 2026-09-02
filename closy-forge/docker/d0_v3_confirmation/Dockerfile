FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0
WORKDIR /app
COPY d0_v3/runner.py /app/base_runner.py
COPY d0_v3_confirmation/runner_v3.py /app/runner_v3.py
COPY d0_v3_confirmation/entrypoint.sh /app/entrypoint.sh
RUN chmod 0555 /app/base_runner.py /app/runner_v3.py /app/entrypoint.sh \
    && find /app -xdev -type f -exec sha256sum {} \; > /app/image-file-sbom.sha256
USER 65532:65532
ENTRYPOINT ["/app/entrypoint.sh"]
