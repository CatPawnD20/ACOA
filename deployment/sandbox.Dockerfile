FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

WORKDIR /opt/acoa-sandbox
ENV ACOA_GENERATED_CODE_SANDBOX=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/acoa-sandbox/src

RUN groupadd --gid 10002 acoa-sandbox \
    && useradd --uid 10002 --gid 10002 --create-home --home-dir /home/acoa-sandbox acoa-sandbox

COPY src/acoa/__init__.py ./src/acoa/
COPY src/acoa/infrastructure/__init__.py src/acoa/infrastructure/sandbox_worker.py ./src/acoa/infrastructure/

USER 10002:10002
ENTRYPOINT ["python", "-m", "acoa.infrastructure.sandbox_worker"]
