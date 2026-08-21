FROM node:22-bookworm

ARG HERMES_VERSION=0.19.0
ARG BMAD_LOOP_VERSION=0.10.0
ARG UV_VERSION=0.8.14
ARG PRIME_AGENT_VERSION=0.7.3
ARG COPILOT_VERSION=latest

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/home/agent/.local/bin:/opt/agent-control/node_modules/.bin:${PATH} \
    PYTHONUNBUFFERED=1 \
    HERMES_HOME=/home/agent/.hermes \
    GIT_CONFIG_GLOBAL=/home/agent/.config/git/config

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git git-lfs jq openssh-client python3 python3-pip \
      python3-venv ripgrep tini tmux unzip && \
    rm -rf /var/lib/apt/lists/*

RUN npm_config_ignore_scripts=false npm install --global \
      "@github/copilot@${COPILOT_VERSION}" opencode-ai "bmad-method@6.11.0"

RUN mkdir -p /opt/bmad-distribution && \
    bmad install --directory /opt/bmad-distribution --modules bmm \
      --tools github-copilot --yes --user-name Usuario \
      --communication-language spanish --document-output-language spanish \
      --output-folder _bmad-output

RUN usermod --login agent --home /home/agent --move-home node && \
    groupmod --new-name agent node && \
    mkdir -p /workspace/project /workspace/output /opt/agent-control && \
    chown -R agent:agent /workspace /opt/agent-control

ENV HOME=/home/agent
ENV BROWSER=/usr/local/bin/lab-open-browser

USER agent
WORKDIR /home/agent

RUN python3 -m venv /home/agent/.venv && \
    /home/agent/.venv/bin/pip install --no-cache-dir \
      "uv==${UV_VERSION}" \
      "hermes-agent[all]==${HERMES_VERSION}" \
      "bmad-loop[opencode,tui] @ git+https://github.com/bmad-code-org/bmad-loop.git@v${BMAD_LOOP_VERSION}"

COPY --chown=agent:agent scripts/python-sitecustomize.py \
  /opt/agent-lab/python/sitecustomize.py
ENV PYTHONPATH=/opt/agent-lab/python

ENV PATH=/home/agent/.venv/bin:/home/agent/.local/bin:/opt/agent-control/node_modules/.bin:${PATH}

# Prime publica artefactos versionados mediante su instalador oficial.
USER root
RUN ln -sf /home/agent/.venv/bin/bmad-loop /usr/local/bin/bmad-loop && \
    ln -sf /home/agent/.venv/bin/hermes /usr/local/bin/hermes && \
    ln -sf /home/agent/.venv/bin/uv /usr/local/bin/uv && \
    printf '%s\n' \
      'export PATH="/home/agent/.venv/bin:/home/agent/.local/bin:/opt/agent-control/node_modules/.bin:$PATH"' \
      >/etc/profile.d/agent-lab-path.sh && \
    chmod 0644 /etc/profile.d/agent-lab-path.sh
RUN curl -fsSL https://app.primeintellect.ai/prime-agent/install.sh -o /tmp/prime-install.sh && \
    VERSION="${PRIME_AGENT_VERSION}" sh /tmp/prime-install.sh && \
    rm /tmp/prime-install.sh && \
    chown -R agent:agent /home/agent/.npm
RUN apt-get update && \
    apt-get install -y --no-install-recommends gh && \
    rm -rf /var/lib/apt/lists/*
USER agent

COPY --chown=agent:agent components/agent-control/package.json \
  components/agent-control/package-lock.json /opt/agent-control/
RUN cd /opt/agent-control && npm ci --omit=dev
COPY --chown=agent:agent components/agent-control/src /opt/agent-control/src

COPY --chown=agent:agent hermes-skills/ /usr/local/share/agent-lab/hermes-skills/
COPY --chown=agent:agent scripts/ /usr/local/lib/agent-lab/

USER root
RUN chmod +x /usr/local/lib/agent-lab/* && \
    ln -sf /usr/local/lib/agent-lab/bmad-loop-safe /usr/local/bin/bmad-loop && \
    ln -s /usr/local/lib/agent-lab/lab /usr/local/bin/lab && \
    ln -s /usr/local/lib/agent-lab/open-browser /usr/local/bin/lab-open-browser
WORKDIR /workspace/project
EXPOSE 9119 9121
ENTRYPOINT ["/usr/local/lib/agent-lab/entrypoint"]
CMD ["serve"]
