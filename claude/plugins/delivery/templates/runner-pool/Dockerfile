# Shared CI pool image (DL30). One image, one agent per repository, started by pool_supervisor.py.
FROM ubuntu:24.04
ARG RUNNER_VERSION=2.338.2
ARG RUNNER_SHA256
LABEL dev.luismc.runner-pool="1"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git tini python3 sudo util-linux postgresql-client libicu74 \
 && rm -rf /var/lib/apt/lists/*
# The runner tarball is checked by SHA-256. The build fails when RUNNER_SHA256 is empty or does not match.
RUN test -n "$RUNNER_SHA256" \
 && curl -fsSL -o /tmp/runner.tgz "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" \
 && echo "${RUNNER_SHA256}  /tmp/runner.tgz" | sha256sum -c - \
 && mkdir -p /opt/runner && tar -xzf /tmp/runner.tgz -C /opt/runner && rm /tmp/runner.tgz \
 && /opt/runner/bin/installdependencies.sh
COPY pool_supervisor.py pool_agents.py /opt/pool/
COPY pool-add-agent pool-remove-agent /usr/local/bin/
COPY hooks/ /opt/delivery/hooks/
# The setup copies the machine-layer scripts (runner_load_gate.py, runner_job_done.py, load.py, machine_slots.py) here.
COPY delivery/ /opt/delivery/
RUN chmod +x /usr/local/bin/pool-add-agent /usr/local/bin/pool-remove-agent /opt/delivery/hooks/*.sh
VOLUME ["/agents"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini", "--", "python3", "/opt/pool/pool_supervisor.py"]
