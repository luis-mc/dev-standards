# Shared CI pool image (DL30). One image, one agent per repository, started by pool_supervisor.py.
FROM ubuntu:24.04
ARG RUNNER_VERSION=2.338.2
ARG RUNNER_SHA256
ARG POOL_BROWSERS=none
# DL149: POOL_LAYERS is a comma list (only `windows-packaging` exists); POOL_APT is a space list from .delivery/pool.apt. Both are checked by the setup.
ARG POOL_LAYERS=
ARG POOL_APT=
# The one place the Playwright version for the system libraries is pinned (DL67).
ARG PLAYWRIGHT_VERSION=1.65.0
LABEL dev.luismc.runner-pool="1"
ENV DEBIAN_FRONTEND=noninteractive
# libatomic1: pnpm's standalone binary (@pnpm/exe) needs it. xz-utils, unzip, zip, jq: common actions assume them, as on hosted runners (DL71).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git tini python3 sudo util-linux postgresql-client libicu74 \
    build-essential pkg-config \
    libatomic1 xz-utils unzip zip jq \
 && rm -rf /var/lib/apt/lists/*
# DL167: cargo-xwin needs clang-cl, lld-link and llvm-lib to build C/C++ crates for x86_64-pc-windows-msvc, and gcc cannot make MSVC-ABI objects.
# Ubuntu keeps these under /usr/lib/llvm-<N>/bin (some only as clang-cl-<N>), so N is found at build time and linked into /usr/local/bin.
# DL169: Ubuntu 24.04 ships no clang-cl at all; clang runs in MSVC mode when called as clang-cl, so clang is linked under that name.
RUN apt-get update \
 && apt-get install -y --no-install-recommends clang lld llvm \
 && rm -rf /var/lib/apt/lists/* \
 && llvmdir="$(ls -d /usr/lib/llvm-* | sort -t- -k2 -n | tail -n 1)" \
 && test -d "$llvmdir/bin" \
 && n="${llvmdir##*-}" \
 && for t in clang-cl lld-link llvm-lib llvm-ar llvm-rc lld; do \
      command -v "$t" >/dev/null 2>&1 && continue; \
      for c in "$llvmdir/bin/$t" "/usr/bin/$t-$n"; do \
        if [ -x "$c" ]; then ln -sf "$c" "/usr/local/bin/$t"; break; fi; \
      done; \
    done \
 && { command -v clang-cl >/dev/null 2>&1 || ln -sf "$llvmdir/bin/clang" /usr/local/bin/clang-cl; }
# DL167: image self-check, so a broken LLVM install fails the build.
RUN clang-cl --version && lld-link --version && llvm-lib /? >/dev/null
# GitHub CLI (DL86): hosted runners preinstall gh, so workflows call `gh api` and `gh pr`. Pinned tarball, checked by SHA-256 like the runner.
ARG GH_VERSION=2.103.3
ARG GH_SHA256=4c806978ffce1cec70853302a56d70ac6da4f19bae7adca4e1a8ab00633dd91d
RUN curl -fsSL -o /tmp/gh.tgz "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
 && echo "${GH_SHA256}  /tmp/gh.tgz" | sha256sum -c - \
 && tar -xzf /tmp/gh.tgz -C /tmp \
 && install -m 0755 "/tmp/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh \
 && rm -rf /tmp/gh.tgz "/tmp/gh_${GH_VERSION}_linux_amd64"
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
# DL149: opt-in apt layers and the project fragment. Off by default (windows-packaging adds about 1 GB).
# Ubuntu 24.04 ships dotnet-sdk-8.0 and wine64 itself, so no Microsoft feed and no i386 architecture are added (64-bit Wine only).
RUN pk=""; \
    case ",$POOL_LAYERS," in *,windows-packaging,*) pk="dotnet-sdk-8.0 wine wine64 xvfb xauth msitools";; esac; \
    pk="$pk $POOL_APT"; \
    if [ -n "$(echo $pk)" ]; then \
      apt-get update && apt-get install -y --no-install-recommends $pk && rm -rf /var/lib/apt/lists/*; \
    fi
COPY pool_supervisor.py pool_agents.py /opt/pool/
COPY pool-add-agent pool-remove-agent /usr/local/bin/
COPY pool-db-env /usr/local/bin/
COPY hooks/ /opt/delivery/hooks/
# The setup copies the machine-layer scripts (runner_load_gate.py, runner_job_done.py, load.py, machine_slots.py) here.
COPY delivery/ /opt/delivery/
RUN chmod +x /usr/local/bin/pool-add-agent /usr/local/bin/pool-remove-agent /usr/local/bin/pool-db-env /opt/delivery/hooks/*.sh
# DL115: the per-runner tool cache (CI_TOOLS_DIR); every agent user writes it, the sticky bit keeps files apart.
RUN mkdir -p /ci-tools && chmod 1777 /ci-tools
VOLUME ["/agents"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini", "--", "python3", "/opt/pool/pool_supervisor.py"]
