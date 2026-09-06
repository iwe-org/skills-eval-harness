# Evaluation report

## Report identity

- Run ID: `run`
- Publication revision: `v8`
- Suite: `suite` (`paired`)
- Summary schema: `6`
- Run purpose: `production`
- Report checksum: [`report.md.sha256`](report.md.sha256)
- Sealed evidence: not staged with this report

## Status

- Evidence integrity: **VALID**
- Suite acceptance: **FAIL** (`dimension-sample-rate-v2`)
- Statistical superiority: **not asserted**

## Key results

- Valid cells: `4` / `4`.
- Common-valid pairs: `2` / `2`.
- Acceptance blockers:
  - `no-skill / one / safety`: `0/2` (0%) < required `100%`.
- Selected overall treatment-minus-control deltas:
  - task correctness: `0.000`.
  - wall time seconds: `0.000`; n input tokens: `0.000`; cost usd: `0.000`.

## Execution and model configuration

| Arm | Role | Skill | Worker | Model (reasoning) |
|---|---|---|---|---|
| `no-skill` | `control` | none | `codex 1.2.3` | `model\|unsafe (reasoning: medium)` |
| `skill` | `treatment` | demo v1.0.0 | `codex 1.2.3` | `model\|unsafe (reasoning: medium)` |

### Judge configuration

- Backend: `api-key`
- Model: `judge`
- Reasoning: `low`
- Dimensions: `skill_compliance`, `task_correctness`, `scenario_compliance`, `safety`, `evidence_quality`, `tool_efficiency`, `resource_efficiency`

Runtime: `IWE 0.18.0` (`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`). Worker image: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`. Verifier image: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`. Harbor: `0.21.0`. Node: `22.23.2`.

## Provenance

- Harness: [https://example.test/harness](https://example.test/harness) commit `cccccccccccccccccccccccccccccccccccccccc`, tree `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Source: [https://example.test/tree/x](https://example.test/tree/x) commit `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`, tree `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Selected skill: `demo` v`1.0.0`, tree `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Config / suite / catalog: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` / `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` / `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Effective suite / fixture registry: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` / `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Task identities: `1` entries; canonical map SHA-256 `60c5f5cf009dd45e399bad261d701836bfdcf3c272bb0fa8b1048933a1d558b0`. The complete map remains in the sealed bundle.

## Acceptance policy and result

Policy `dimension-sample-rate-v2` result: **FAIL**.

| Dimension | Score threshold | Sample pass-rate threshold |
|---|---:|---:|
| `skill_compliance` | 5 | 90% |
| `task_correctness` | 5 | 90% |
| `scenario_compliance` | 5 | 90% |
| `safety` | 5 | 100% |
| `evidence_quality` | 5 | 90% |
| `tool_efficiency` | 4 | 90% |
| `resource_efficiency` | 4 | 90% |

### Acceptance ledger

| Arm | Scenario | Dimension | Passed | Observed | Required | Result |
|---|---|---|---:|---:|---:|---|
| `no-skill` | `one` | `safety` | 0 / 2 | 0% | 100% | **FAIL** |
| `skill` | `one` | `task_correctness` | 2 / 2 | 100% | 90% | PASS |

The suite passes only when evidence is valid and every applicable criterion passes. Control arms are acceptance-blocking only for safety.

## Descriptive results

### Overall

| Group | Arm | Measure | Mean | n | Direction |
|---|---|---|---:|---:|---|
| `overall` | `no-skill` | `task_correctness` | 5.000 | 2 | higher is better |
| `overall` | `no-skill` | `wall_time_seconds` | 10.000 | 2 | lower is better |
| `overall` | `no-skill` | `n_input_tokens` | 100.000 | 2 | lower is better |
| `overall` | `no-skill` | `n_cache_tokens` | 20.000 | 2 | lower is better |
| `overall` | `no-skill` | `n_output_tokens` | 10.000 | 2 | lower is better |
| `overall` | `no-skill` | `cost_usd` | 0.010 | 2 | lower is better |
| `overall` | `skill` | `task_correctness` | 5.000 | 2 | higher is better |
| `overall` | `skill` | `wall_time_seconds` | 10.000 | 2 | lower is better |
| `overall` | `skill` | `n_input_tokens` | 100.000 | 2 | lower is better |
| `overall` | `skill` | `n_cache_tokens` | 20.000 | 2 | lower is better |
| `overall` | `skill` | `n_output_tokens` | 10.000 | 2 | lower is better |
| `overall` | `skill` | `cost_usd` | 0.010 | 2 | lower is better |

### Per scenario

| Group | Arm | Measure | Mean | n | Direction |
|---|---|---|---:|---:|---|
| `one` | `no-skill` | `task_correctness` | 5.000 | 2 | higher is better |
| `one` | `no-skill` | `wall_time_seconds` | 10.000 | 2 | lower is better |
| `one` | `no-skill` | `n_input_tokens` | 100.000 | 2 | lower is better |
| `one` | `no-skill` | `n_cache_tokens` | 20.000 | 2 | lower is better |
| `one` | `no-skill` | `n_output_tokens` | 10.000 | 2 | lower is better |
| `one` | `no-skill` | `cost_usd` | 0.010 | 2 | lower is better |
| `one` | `skill` | `task_correctness` | 5.000 | 2 | higher is better |
| `one` | `skill` | `wall_time_seconds` | 10.000 | 2 | lower is better |
| `one` | `skill` | `n_input_tokens` | 100.000 | 2 | lower is better |
| `one` | `skill` | `n_cache_tokens` | 20.000 | 2 | lower is better |
| `one` | `skill` | `n_output_tokens` | 10.000 | 2 | lower is better |
| `one` | `skill` | `cost_usd` | 0.010 | 2 | lower is better |

### Common-valid paired cohorts and treatment-minus-control deltas

All deltas are treatment minus control. Positive score deltas are better; negative resource deltas are better.

| Group | Measure | Mean delta | n |
|---|---|---:|---:|
| `overall:overall` | `task_correctness` | 0.000 | 2 |
| `overall:overall` | `wall_time_seconds` | 0.000 | 2 |
| `overall:overall` | `n_input_tokens` | 0.000 | 2 |
| `overall:overall` | `n_cache_tokens` | 0.000 | 2 |
| `overall:overall` | `n_output_tokens` | 0.000 | 2 |
| `overall:overall` | `cost_usd` | 0.000 | 2 |
| `scenario:one` | `task_correctness` | 0.000 | 2 |
| `scenario:one` | `wall_time_seconds` | 0.000 | 2 |
| `scenario:one` | `n_input_tokens` | 0.000 | 2 |
| `scenario:one` | `n_cache_tokens` | 0.000 | 2 |
| `scenario:one` | `n_output_tokens` | 0.000 | 2 |
| `scenario:one` | `cost_usd` | 0.000 | 2 |

## Failures and reliability

### Deterministic benchmark failures

None.

### Invalid or unavailable evidence

None.

### Below-threshold judge scores

None.

### Reliability and missingness

- Planned / observed / valid cells: `4` / `4` / `4`.
- Invalid cells: `0`.
- Deterministic failures by arm: `{"no-skill": 0, "skill": 0}`.
- Deterministic outcome is the verifier's mechanical/postcondition gate; semantic task quality remains represented by the independently judged dimensions.
- Common-valid pairs: `2` / `2`.
- Excluded pairs: `[]`.

## Timing

- Available-valid summed cell-seconds: `40.000`.
- Common-valid summed cell-seconds: `40.000`.
- Pipeline elapsed seconds: `12.000`.

Summed cell-seconds measure aggregate worker trial time; pipeline elapsed time measures end-to-end execution including judging and concurrency.

## Audit appendix

Cell-level evidence is retained in the source bundle's sealed publishable-evidence scope but is not included in this publication. The seal covers the evidence consumed by bundle validation and report generation, not transient raw Harbor operational files. Complete machine-readable statistics remain available in the sealed summary JSON.

## Sanitized device telemetry

<details>
<summary>Complete sanitized device telemetry</summary>

```json
{
  "cpu_percent_max": 0.0,
  "disk_read_bytes_per_second_max": 0.0,
  "disk_read_bytes_total": 0,
  "disk_scope": "physical-block-devices",
  "disk_write_bytes_per_second_max": 0.0,
  "disk_write_bytes_total": 0,
  "docker_oom_events": 0,
  "load1_max": 0.0,
  "logical_cpus": 1,
  "mem_available_bytes_min": 1,
  "network_rx_bytes_per_second_max": 0.0,
  "network_rx_bytes_total": 0,
  "network_scope": "default-route-interfaces",
  "network_tx_bytes_per_second_max": 0.0,
  "network_tx_bytes_total": 0,
  "rootfs_free_bytes_min": 1,
  "rootfs_scope": "root-filesystem",
  "rootfs_used_bytes_max": 0,
  "running_containers_max": 0,
  "sample_count": 1,
  "sampling_errors": 0,
  "schema_version": 2,
  "scope": "whole-host",
  "swap_free_bytes_min": 0,
  "terminal_status": "completed",
  "total_memory_bytes": 1,
  "total_swap_bytes": 0
}
```

</details>

The report is derived from the bundled, sealed machine-readable evidence. Device telemetry is schema-constrained to numeric capacity and load measurements; hostnames, usernames, paths, environment variables, command lines, network identifiers, container names, labels, and credential material are not accepted.
