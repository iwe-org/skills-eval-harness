FROM docker.io/library/python@sha256:8fef26df932191825664e4957ff488c96dfe64918327634a357a55facbc994d3
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates curl nodejs npm procps ripgrep \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g node@22.23.2 \
    && test "$(node --version)" = "v22.23.2"
RUN npm install -g @openai/codex@0.147.0 @anthropic-ai/claude-code@2.1.233 \
    && test "$(codex --version)" = "codex-cli 0.147.0" \
    && claude --version | grep -F "2.1.233" \
    && rm -rf /root/.npm
