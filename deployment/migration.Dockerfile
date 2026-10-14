FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

WORKDIR /opt/acoa-migrations
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY migration-requirements.txt ./
RUN python -m pip --isolated install --index-url https://pypi.org/simple pip==26.2.1
RUN python -m pip --isolated install --index-url https://pypi.org/simple -r migration-requirements.txt
COPY migrate.py alembic.ini ./
COPY migrations/ ./migrations/
ENTRYPOINT ["python", "migrate.py"]
