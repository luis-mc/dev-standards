# Shared CI pool image (DL30). One image, one agent per repository, started by pool_supervisor.py.
FROM ubuntu:24.04
ARG RUNNER_VERSION=2.338.2
ARG RUNNER_SHA256
ARG POOL_BROWSERS=none
# The one place the Playwright version for the system libraries is pinned (DL67).
ARG PLAYWRIGHT_VERSION=1.62.1
LABEL dev.luismc.runner-pool="1"
ENV DEBIAN_FRONTEND=noninteractive
# libatomic1: pnpm's standalone binary (@pnpm/exe) needs it. xz-utils, unzip, zip, jq: common actions assume them, as on hosted runners (DL71).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git tini python3 sudo util-linux postgresql-client libicu74 \
    libatomic1 xz-utils unzip zip jq \
 && rm -rf /var/lib/apt/lists/*
# The runner tarball is checked by SHA-256. The build fails when RUNNER_SHA256 is empty or does not match.
RUN test -n "$RUNNER_SHA256" \
 && curl -fsSL -o /tmp/runner.tgz "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" \
 && echo "${RUNNER_SHA256}  /tmp/runner.tgz" | sha256sum -c - \
 && mkdir -p /opt/runner && tar -xzf /tmp/runner.tgz -C /opt/runner && rm /tmp/runner.tgz \
 && /opt/runner/bin/installdependencies.sh
# Opt-in (POOL_BROWSERS=chromium): the Chromium system libraries, installed here as root because job users have no sudo.
# The browser itself stays per job: `playwright install chromium` without --with-deps.
# Playwright needs Node 20 or newer and Ubuntu 24.04 ships Node 18, so this step uses the official Node LTS tarball,
# checked by SHA-256 like the runner, only to run install-deps, and removes it afterwards (DL76).
ARG NODE_VERSION=22.23.4
ARG NODE_SHA256=1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce
RUN if [ "$POOL_BROWSERS" = "chromium" ]; then \
      curl -fsSL -o /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
      && echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c - \
      && mkdir -p /opt/node-build && tar -xJf /tmp/node.tar.xz -C /opt/node-build --strip-components=1 && rm /tmp/node.tar.xz \
      && apt-get update \
      && PATH="/opt/node-build/bin:$PATH" npx -y playwright@${PLAYWRIGHT_VERSION} install-deps chromium \
      && rm -rf /opt/node-build /var/lib/apt/lists/* /root/.npm; \
    fi
COPY pool_supervisor.py pool_agents.py /opt/pool/
COPY pool-add-agent pool-remove-agent /usr/local/bin/
COPY pool-db-env /usr/local/bin/
COPY hooks/ /opt/delivery/hooks/
# The setup copies the machine-layer scripts (runner_load_gate.py, runner_job_done.py, load.py, machine_slots.py) here.
COPY delivery/ /opt/delivery/
RUN chmod +x /usr/local/bin/pool-add-agent /usr/local/bin/pool-remove-agent /usr/local/bin/pool-db-env /opt/delivery/hooks/*.sh
VOLUME ["/agents"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini", "--", "python3", "/opt/pool/pool_supervisor.py"]
