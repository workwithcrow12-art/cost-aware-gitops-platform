FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir '.[aws]'

USER 10001:10001
ENTRYPOINT ["finops"]
CMD ["report"]
