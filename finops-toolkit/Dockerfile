FROM python:3.14.10-alpine3.24@sha256:5862d971d1f0ae26b258cefa4e893556b1d3aba81bd2ff30888704ad378bab67 AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-compile --prefix=/install '.[aws]'

FROM python:3.14.10-alpine3.24@sha256:5862d971d1f0ae26b258cefa4e893556b1d3aba81bd2ff30888704ad378bab67

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /install /usr/local
RUN addgroup -g 10001 -S finops \
    && adduser -u 10001 -G finops -H -D -S -s /sbin/nologin finops \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip

WORKDIR /app
USER 10001:10001
ENTRYPOINT ["finops"]
CMD ["report"]
