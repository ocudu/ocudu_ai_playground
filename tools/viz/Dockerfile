# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

# ocudu-viz image. Build context: the tools/ directory, e.g. "docker build -f viz/Dockerfile ." from tools/.
# The ocudu-viz wrapper script builds and runs it.

FROM node:22-alpine AS frontend
WORKDIR /build/viz/frontend
COPY viz/frontend/package.json viz/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY viz/frontend/ ./
# Writes the bundle and its third-party licenses to /build/viz/viz/static.
RUN npm run build

FROM python:3.12-slim
# Lets the wrapper find the images it built, e.g. to remove the ones replaced by a rebuild.
LABEL org.ocudu.tool="ocudu-viz"
# tshark decodes the pcaps.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tshark \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY parsers ./parsers
COPY viz ./viz
COPY --from=frontend /build/viz/viz/static ./viz/viz/static
RUN pip install --no-cache-dir ./parsers ./viz && rm -rf /src
WORKDIR /
# The server listens on all interfaces of the container; the wrapper publishes the port on the host loopback only.
ENTRYPOINT ["ocudu-viz", "--host", "0.0.0.0", "--no-browser"]
