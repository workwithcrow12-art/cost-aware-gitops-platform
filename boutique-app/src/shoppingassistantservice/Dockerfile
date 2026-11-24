# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

ARG BUILDPLATFORM=linux/amd64

FROM --platform=$BUILDPLATFORM python:3.14.10-alpine3.24@sha256:5862d971d1f0ae26b258cefa4e893556b1d3aba81bd2ff30888704ad378bab67 AS base

FROM base AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk add --no-cache build-base libffi-dev postgresql-dev

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix="/install" -r requirements.txt

FROM base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT="8080"

RUN apk add --no-cache libpq libstdc++ \
    && addgroup -g 1000 -S app \
    && adduser -u 1000 -G app -H -D -S -s /sbin/nologin app

WORKDIR /shoppingassistantservice
COPY --from=builder /install /usr/local
RUN python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip

COPY shoppingassistantservice.py test_shoppingassistantservice.py ./

USER 1000:1000
EXPOSE 8080
ENTRYPOINT ["python", "shoppingassistantservice.py"]
