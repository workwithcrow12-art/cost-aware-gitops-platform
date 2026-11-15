FROM python:3.14.7-alpine@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir '.[aws]'

USER 10001:10001
ENTRYPOINT ["finops"]
CMD ["report"]
