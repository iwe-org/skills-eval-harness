# Default-skill correctness and efficiency

## Purpose

This absolute suite evaluates the selected IWE skill and exact IWE runtime across the scenario catalog declared in `evals/suites/default-skill.yaml`.

## Contract

- `evals/config.yaml`, the suite YAML, and `evals/scenarios/iwe.yaml` are strict inputs.
- The skill source must resolve to a clean, exact Git commit and content digest.
- The runtime must print the exact requested version and is hashed before use.
- Every scenario becomes a Harbor task with a pinned base-image digest.
- The worker uses an allowlisted network policy. Deterministic verification runs in a separate no-network container.
- Judge output is schema-validated locally and every metric must cite known evidence IDs.
- Missing, duplicate, invalid, unfinished, or shared-verifier cells fail closed.

## Smoke run

Materialize the pinned fixture repositories first, then run one scenario and one sample:

```bash
export IWE_RUNTIME=/absolute/path/to/iwe
export SEVENTEEN_CENTURIES=/absolute/path/to/seventeen-centuries
export PKM_DEMO=/absolute/path/to/pkm-demo
export CODEX_AUTH_JSON="$HOME/.codex-harbor/auth.json"
export OUTPUT=/absolute/new/path/default-skill-smoke

test ! -e "$OUTPUT"

uv run skills-eval run \
  --suite evals/suites/default-skill.yaml \
  --skill-source https://github.com/iwe-org/skills/tree/f571d6f83dd79407ec64caf7cc3036708062e3c8/skills/iwe-v18 \
  --runtime "$IWE_RUNTIME" \
  --runtime-version 0.18.0 \
  --fixture "seventeen-centuries=$SEVENTEEN_CENTURIES" \
  --fixture "pkm-demo=$PKM_DEMO" \
  --agent codex \
  --codex-auth chatgpt \
  --codex-auth-json "$CODEX_AUTH_JSON" \
  --judge-auth chatgpt \
  --scenario read-one-known-note \
  --samples 1 \
  --jobs 1 \
  --judge-jobs 4 \
  --cache "$HOME/.cache/skills-eval" \
  --run-purpose diagnostic \
  --output "$OUTPUT"
```

Use `--agent claude` for Claude Code. The command forwards only that agent's provider key. It does not read or copy Codex `auth.json`, Claude host state, `.env`, cloud credentials, or unrelated tokens.

## Production run

Set the machine-specific paths and choose a fresh output directory. The production suite materializes the full scenario catalog with ten samples per scenario and the single `skill` arm.

```bash
export IWE_RUNTIME=/absolute/path/to/iwe
export SEVENTEEN_CENTURIES=/absolute/path/to/seventeen-centuries
export PKM_DEMO=/absolute/path/to/pkm-demo
export CODEX_AUTH_JSON="$HOME/.codex-harbor/auth.json"
export OUTPUT=/absolute/new/path/default-skill-production

test ! -e "$OUTPUT"

uv run skills-eval run \
  --suite evals/suites/default-skill.yaml \
  --skill-source https://github.com/iwe-org/skills/tree/f571d6f83dd79407ec64caf7cc3036708062e3c8/skills/iwe-v18 \
  --runtime "$IWE_RUNTIME" \
  --runtime-version 0.18.0 \
  --fixture "seventeen-centuries=$SEVENTEEN_CENTURIES" \
  --fixture "pkm-demo=$PKM_DEMO" \
  --agent codex \
  --codex-auth chatgpt \
  --codex-auth-json "$CODEX_AUTH_JSON" \
  --judge-auth chatgpt \
  --jobs 4 \
  --judge-jobs 4 \
  --cache "$HOME/.cache/skills-eval" \
  --run-purpose production \
  --output "$OUTPUT"
```

Use `--jobs 4` for this single-arm benchmark. Unlike the paired A/B suite, it does not compare wall time between arms, so four concurrent worker trials improve throughput without changing a paired timing comparison.

## Production acceptance

A production report may be published only from a complete schema-v6 Harbor run with valid evidence and a clean harness tree. A valid acceptance failure remains publishable as an observed result. The publisher recomputes the summary, validates provenance, derives the canonical repository from the Git remote, refuses replacement, and emits and links a SHA-256 sidecar.

The report uses the common identity/status, arm/model, judge, provenance, acceptance, overall/per-scenario results, failures/reliability, timing, and audit contract. Absolute reports do not contain paired cohorts, deltas, exclusions, or superiority language.
