FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0
WORKDIR /app
COPY runner.py /app/runner.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod 0555 /app/runner.py /app/entrypoint.sh \
    && find /app -xdev -type f -exec sha256sum {} \; > /app/image-file-sbom.sha256
USER 65532:65532
ENTRYPOINT ["/app/entrypoint.sh"]
