FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

WORKDIR /opt/acoa-browser
ENV ACOA_BROWSER_SANDBOX=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/acoa-browser/src \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY deployment/browser-requirements.txt ./
RUN python -m pip --isolated install --index-url https://pypi.org/simple pip==26.2.1 \
    && python -m pip --isolated install --index-url https://pypi.org/simple -r browser-requirements.txt \
    && python -m playwright install --with-deps chromium \
    && groupadd --gid 10001 acoa-browser \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/acoa-browser acoa-browser \
    && chmod -R a=rX /ms-playwright

COPY src/acoa/__init__.py ./src/acoa/
COPY src/acoa/infrastructure/__init__.py src/acoa/infrastructure/browser_worker.py ./src/acoa/infrastructure/

USER 10001:10001
ENTRYPOINT ["python", "-m", "acoa.infrastructure.browser_worker"]
