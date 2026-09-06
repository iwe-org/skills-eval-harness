# Skill-guidance efficiency A/B

## Purpose

This paired suite measures the effect of the selected skill relative to the same runtime without skill guidance. `evals/suites/skill-guidance-ab.yaml` is the suite SSOT.

## Pairing and containment

Each `(scenario, sample)` pair is run as two separate Harbor jobs:

- `skill`: Harbor injects the resolved skill.
- `no-skill`: no skill is injected.

The generated task bytes, pinned image, runtime, fixture, instruction, resource limits, agent implementation, network allowlist, timeout, verifier image, and verifier policy are identical. Only Harbor's skill injection option differs. A preflight rejects structural drift.

Both Codex and Claude Code use the same Harbor Docker environment implementation. Only explicitly selected credentials are staged. Deterministic verification runs in a separate no-network container.

## Judge safety

The worker trajectory, command telemetry, workspace manifest, and oracle data are serialized as an untrusted JSON evidence envelope. They are never concatenated into the judge's system instruction. Judge output must match the strict schema, contain all seven dimensions, include substantive rationales, and cite only known evidence IDs. Bare scores and unknown citations are invalid cells.

## Smoke run

Set the machine-specific paths first. The output directory must not already exist:

```bash
export IWE_RUNTIME=/absolute/path/to/iwe
export PKM_DEMO=/absolute/path/to/pkm-demo
export CODEX_AUTH_JSON="$HOME/.codex-harbor/auth.json"
export OUTPUT=/absolute/new/path/skill-guidance-ab-smoke

test ! -e "$OUTPUT"

uv run skills-eval run \
  --suite evals/suites/skill-guidance-ab-smoke.yaml \
  --skill-source https://github.com/iwe-org/skills/tree/f571d6f83dd79407ec64caf7cc3036708062e3c8/skills/iwe-v18 \
  --runtime "$IWE_RUNTIME" \
  --runtime-version 0.18.0 \
  --fixture "pkm-demo=$PKM_DEMO" \
  --agent codex \
  --codex-auth chatgpt \
  --codex-auth-json "$CODEX_AUTH_JSON" \
  --judge-auth chatgpt \
  --jobs 2 \
  --judge-jobs 4 \
  --cache "$HOME/.cache/skills-eval" \
  --run-purpose diagnostic \
  --output "$OUTPUT"
```

This materializes one scenario, one sample, and two arms: two worker cells and one paired observation. `--jobs 2` is the global Harbor trial ceiling, split as `1 + 1` across the paired arms; it is not multiplied by the arm count.

Run the same bounded smoke with `--agent claude` before expanding the matrix. Full runs are paid and should follow smoke repair cycles.

## Production run

Use a fresh output directory. This command materializes six scenarios, ten samples, and two arms: 120 worker cells and 60 paired observations.

```bash
export IWE_RUNTIME=/absolute/path/to/iwe
export SEVENTEEN_CENTURIES=/absolute/path/to/seventeen-centuries
export PKM_DEMO=/absolute/path/to/pkm-demo
export CODEX_AUTH_JSON="$HOME/.codex-harbor/auth.json"
export OUTPUT=/absolute/new/path/skill-guidance-ab-production

test ! -e "$OUTPUT"

uv run skills-eval run \
  --suite evals/suites/skill-guidance-ab.yaml \
  --skill-source https://github.com/iwe-org/skills/tree/f571d6f83dd79407ec64caf7cc3036708062e3c8/skills/iwe-v18 \
  --runtime "$IWE_RUNTIME" \
  --runtime-version 0.18.0 \
  --fixture "seventeen-centuries=$SEVENTEEN_CENTURIES" \
  --fixture "pkm-demo=$PKM_DEMO" \
  --agent codex \
  --codex-auth chatgpt \
  --codex-auth-json "$CODEX_AUTH_JSON" \
  --judge-auth chatgpt \
  --jobs 2 \
  --judge-jobs 4 \
  --cache "$HOME/.cache/skills-eval" \
  --run-purpose production \
  --output "$OUTPUT"
```

Keep `--jobs 2` for this paired benchmark. Its wall-time comparison is part of the measured outcome, so changing worker concurrency changes the execution conditions being compared.

## Provenance and publication

The run records exact source and harness commits, tree hashes for the source and selected skill, runtime identity, suite, scenario catalog and frozen config, Harbor task checksums, image digests, Harbor version, and sanitized numeric device telemetry. Publication rejects dirty, incomplete, structurally invalid, mismatched, sensitive-telemetry, or already-published inputs. A structurally valid benchmark failure remains publishable as an observed outcome. Publication stages the report and checksum by default; `--include-evidence` additionally stages the complete sealed evidence bundle. There is no compatibility path for old TOML manifests or old host-process reports.

The schema-v6 report uses the common identity/status, arm/model, judge, provenance, acceptance, overall/per-scenario results, failures/reliability, timing, and audit contract. It additionally reports common-valid cohorts, treatment-minus-control deltas, excluded pairs, and explicitly distinguishes threshold acceptance from an unasserted statistical-superiority verdict. Every other summary version is unsupported and fails closed.
