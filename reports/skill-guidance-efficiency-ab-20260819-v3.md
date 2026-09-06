# Evaluation report

## Report identity

- Run ID: `skill-guidance-ab-production-20260819-v3`
- Publication revision: `v3`
- Suite: `skill-guidance-efficiency-ab` (`paired`)
- Summary schema: `6`
- Run purpose: `production`
- Report checksum: [`skill-guidance-efficiency-ab-20260819-v3.md.sha256`](skill-guidance-efficiency-ab-20260819-v3.md.sha256)
- Sealed evidence: not staged with this report

## Status

- Evidence integrity: **VALID**
- Suite acceptance: **PASS** (`dimension-sample-rate-v2`)
- Statistical superiority: **not asserted**

## Key results

- Valid cells: `120` / `120`.
- Common-valid pairs: `60` / `60`.
- Acceptance blockers: none.
- Selected overall treatment-minus-control deltas:
  - task correctness: `0.617`; scenario compliance: `1.083`; tool efficiency: `2.800`; resource efficiency: `2.667`.
  - wall time seconds: `-7.954`; n input tokens: `-26668.850`; cost usd: `-0.002090`.

## Execution and model configuration

| Arm | Role | Skill | Worker | Model (reasoning) |
|---|---|---|---|---|
| `no-skill` | `control` | none | `codex 0.147.0` | `openai/gpt-5.6-luna (reasoning: medium)` |
| `skill` | `treatment` | iwe-v18 v0.9.9 | `codex 0.147.0` | `openai/gpt-5.6-luna (reasoning: medium)` |

### Judge configuration

- Backend: `chatgpt`
- Model: `gpt-5.6-sol`
- Reasoning: `low`
- Dimensions: `skill_compliance`, `task_correctness`, `scenario_compliance`, `safety`, `evidence_quality`, `tool_efficiency`, `resource_efficiency`

Runtime: `IWE 0.18.0` (`12eb77af823b04472a2b92ceb0d5bacef4e1eda1b38ba0dadfe8f7c33a86ce6c`). Worker image: `778452e0c755ab2d7b5b79ebf3a1ed099cbc9942a7225717e7da108c3a5b3751`. Verifier image: `8fef26df932191825664e4957ff488c96dfe64918327634a357a55facbc994d3`. Harbor: `0.21.0`. Node: `22.23.2`.

## Provenance

- Harness: [https://github.com/bulbigood/skills-eval-harness](https://github.com/bulbigood/skills-eval-harness) commit `bde5696a8d27f87bad29050e5cfa9cab7bfa3595`, tree `fcc704e4c1f62057c69366a266b17c0c5e0822b44afe1f454c4ee6cf9ad34c91`
- Source: [https://github.com/iwe-org/skills/tree/f571d6f83dd79407ec64caf7cc3036708062e3c8/skills/iwe-v18](https://github.com/iwe-org/skills/tree/f571d6f83dd79407ec64caf7cc3036708062e3c8/skills/iwe-v18) commit `f571d6f83dd79407ec64caf7cc3036708062e3c8`, tree `836c4fec4759c0706cb52d21493e2ed981b3cc0a8168226d37ee80e9b265f3e6`
- Selected skill: `iwe-v18` v`0.9.9`, tree `ca4b120faa5374bc16d5a221d3ccc853aa64ded5c3df0be197ef6a38a01281b9`
- Config / suite / catalog: `382f002738f1c4feb3d1f991fe551db6dc1cec49bff0a4114f874a945a617c62` / `7629985983246c00dc8f88f7e8f487c23bd5b13d09bd16048c1b18e2d28c8844` / `bffbf14da62f9cb39f3f7321dc92e70b88b940d3e569952a517f10be5ac56a84`
- Effective suite / fixture registry: `4213d01e80dce9ce48534637343ded745e6a97a208e20f595fde63778bbf916c` / `bce1af055f3740a1a0eafa86c743acc9bd73cf4deacb917da7db6159fb58e852`
- Task identities: `120` entries; canonical map SHA-256 `571dae6acd00004f42c75c079cfd0873d9a860dfed880ae061ed6b9abd070cf1`. The complete map remains in the sealed bundle.

## Acceptance policy and result

Policy `dimension-sample-rate-v2` result: **PASS**.

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
| `no-skill` | `ambiguous-discovery-with-one-follow-up` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `no-skill` | `discover-and-retrieve-bounded-multi-hop-context` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `no-skill` | `list-and-sort-typed-notes` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `no-skill` | `query-structured-metadata-without-scanning-files` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `no-skill` | `read-one-note-with-parent-context` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `no-skill` | `summarize-one-topic` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `skill` | `ambiguous-discovery-with-one-follow-up` | `skill_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `ambiguous-discovery-with-one-follow-up` | `task_correctness` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `ambiguous-discovery-with-one-follow-up` | `scenario_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `ambiguous-discovery-with-one-follow-up` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `skill` | `ambiguous-discovery-with-one-follow-up` | `evidence_quality` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `ambiguous-discovery-with-one-follow-up` | `tool_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `ambiguous-discovery-with-one-follow-up` | `resource_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `discover-and-retrieve-bounded-multi-hop-context` | `skill_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `discover-and-retrieve-bounded-multi-hop-context` | `task_correctness` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `discover-and-retrieve-bounded-multi-hop-context` | `scenario_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `discover-and-retrieve-bounded-multi-hop-context` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `skill` | `discover-and-retrieve-bounded-multi-hop-context` | `evidence_quality` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `discover-and-retrieve-bounded-multi-hop-context` | `tool_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `discover-and-retrieve-bounded-multi-hop-context` | `resource_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `list-and-sort-typed-notes` | `skill_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `list-and-sort-typed-notes` | `task_correctness` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `list-and-sort-typed-notes` | `scenario_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `list-and-sort-typed-notes` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `skill` | `list-and-sort-typed-notes` | `evidence_quality` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `list-and-sort-typed-notes` | `tool_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `list-and-sort-typed-notes` | `resource_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `query-structured-metadata-without-scanning-files` | `skill_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `query-structured-metadata-without-scanning-files` | `task_correctness` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `query-structured-metadata-without-scanning-files` | `scenario_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `query-structured-metadata-without-scanning-files` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `skill` | `query-structured-metadata-without-scanning-files` | `evidence_quality` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `query-structured-metadata-without-scanning-files` | `tool_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `query-structured-metadata-without-scanning-files` | `resource_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `read-one-note-with-parent-context` | `skill_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `read-one-note-with-parent-context` | `task_correctness` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `read-one-note-with-parent-context` | `scenario_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `read-one-note-with-parent-context` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `skill` | `read-one-note-with-parent-context` | `evidence_quality` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `read-one-note-with-parent-context` | `tool_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `read-one-note-with-parent-context` | `resource_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `summarize-one-topic` | `skill_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `summarize-one-topic` | `task_correctness` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `summarize-one-topic` | `scenario_compliance` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `summarize-one-topic` | `safety` | 10 / 10 | 100% | 100% | PASS |
| `skill` | `summarize-one-topic` | `evidence_quality` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `summarize-one-topic` | `tool_efficiency` | 10 / 10 | 100% | 90% | PASS |
| `skill` | `summarize-one-topic` | `resource_efficiency` | 10 / 10 | 100% | 90% | PASS |

The suite passes only when evidence is valid and every applicable criterion passes. Control arms are acceptance-blocking only for safety.

## Descriptive results

### Overall

| Group | Arm | Measure | Mean | n | Direction |
|---|---|---|---:|---:|---|
| `overall` | `no-skill` | `task_correctness` | 4.383 | 60 | higher is better |
| `overall` | `no-skill` | `scenario_compliance` | 3.917 | 60 | higher is better |
| `overall` | `no-skill` | `safety` | 5.000 | 60 | higher is better |
| `overall` | `no-skill` | `evidence_quality` | 4.700 | 60 | higher is better |
| `overall` | `no-skill` | `tool_efficiency` | 2.183 | 60 | higher is better |
| `overall` | `no-skill` | `resource_efficiency` | 2.300 | 60 | higher is better |
| `overall` | `no-skill` | `wall_time_seconds` | 65.257 | 60 | lower is better |
| `overall` | `no-skill` | `n_input_tokens` | 77903.467 | 60 | lower is better |
| `overall` | `no-skill` | `n_cache_tokens` | 62088.533 | 60 | lower is better |
| `overall` | `no-skill` | `n_output_tokens` | 825.067 | 60 | lower is better |
| `overall` | `no-skill` | `cost_usd` | 0.005395 | 60 | lower is better |
| `overall` | `skill` | `skill_compliance` | 5.000 | 60 | higher is better |
| `overall` | `skill` | `task_correctness` | 5.000 | 60 | higher is better |
| `overall` | `skill` | `scenario_compliance` | 5.000 | 60 | higher is better |
| `overall` | `skill` | `safety` | 5.000 | 60 | higher is better |
| `overall` | `skill` | `evidence_quality` | 5.000 | 60 | higher is better |
| `overall` | `skill` | `tool_efficiency` | 4.983 | 60 | higher is better |
| `overall` | `skill` | `resource_efficiency` | 4.967 | 60 | higher is better |
| `overall` | `skill` | `wall_time_seconds` | 57.303 | 60 | lower is better |
| `overall` | `skill` | `n_input_tokens` | 51234.617 | 60 | lower is better |
| `overall` | `skill` | `n_cache_tokens` | 41762.133 | 60 | lower is better |
| `overall` | `skill` | `n_output_tokens` | 479.283 | 60 | lower is better |
| `overall` | `skill` | `cost_usd` | 0.003305 | 60 | lower is better |

### Per scenario

| Group | Arm | Measure | Mean | n | Direction |
|---|---|---|---:|---:|---|
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `scenario_compliance` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `safety` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `tool_efficiency` | 4.400 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `resource_efficiency` | 4.400 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `wall_time_seconds` | 56.383 | 10 | lower is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `n_input_tokens` | 48732.500 | 10 | lower is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `n_cache_tokens` | 39808.000 | 10 | lower is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `n_output_tokens` | 396.600 | 10 | lower is better |
| `ambiguous-discovery-with-one-follow-up` | `no-skill` | `cost_usd` | 0.003057 | 10 | lower is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `skill_compliance` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `scenario_compliance` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `safety` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `tool_efficiency` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `resource_efficiency` | 5.000 | 10 | higher is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `wall_time_seconds` | 56.887 | 10 | lower is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `n_input_tokens` | 62108.900 | 10 | lower is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `n_cache_tokens` | 50278.400 | 10 | lower is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `n_output_tokens` | 423.300 | 10 | lower is better |
| `ambiguous-discovery-with-one-follow-up` | `skill` | `cost_usd` | 0.003880 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `scenario_compliance` | 4.100 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `safety` | 5.000 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `tool_efficiency` | 1.300 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `resource_efficiency` | 1.300 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `wall_time_seconds` | 74.468 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `n_input_tokens` | 94400.200 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `n_cache_tokens` | 68428.800 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `n_output_tokens` | 1300.900 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `no-skill` | `cost_usd` | 0.008124 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `skill_compliance` | 5.000 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `scenario_compliance` | 5.000 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `safety` | 5.000 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `tool_efficiency` | 5.000 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `resource_efficiency` | 4.900 | 10 | higher is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `wall_time_seconds` | 63.841 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `n_input_tokens` | 51845.800 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `n_cache_tokens` | 40985.600 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `n_output_tokens` | 803.500 | 10 | lower is better |
| `discover-and-retrieve-bounded-multi-hop-context` | `skill` | `cost_usd` | 0.003956 | 10 | lower is better |
| `list-and-sort-typed-notes` | `no-skill` | `task_correctness` | 2.900 | 10 | higher is better |
| `list-and-sort-typed-notes` | `no-skill` | `scenario_compliance` | 3.500 | 10 | higher is better |
| `list-and-sort-typed-notes` | `no-skill` | `safety` | 5.000 | 10 | higher is better |
| `list-and-sort-typed-notes` | `no-skill` | `evidence_quality` | 4.400 | 10 | higher is better |
| `list-and-sort-typed-notes` | `no-skill` | `tool_efficiency` | 1.300 | 10 | higher is better |
| `list-and-sort-typed-notes` | `no-skill` | `resource_efficiency` | 1.400 | 10 | higher is better |
| `list-and-sort-typed-notes` | `no-skill` | `wall_time_seconds` | 62.433 | 10 | lower is better |
| `list-and-sort-typed-notes` | `no-skill` | `n_input_tokens` | 75875.100 | 10 | lower is better |
| `list-and-sort-typed-notes` | `no-skill` | `n_cache_tokens` | 63590.400 | 10 | lower is better |
| `list-and-sort-typed-notes` | `no-skill` | `n_output_tokens` | 716.000 | 10 | lower is better |
| `list-and-sort-typed-notes` | `no-skill` | `cost_usd` | 0.004588 | 10 | lower is better |
| `list-and-sort-typed-notes` | `skill` | `skill_compliance` | 5.000 | 10 | higher is better |
| `list-and-sort-typed-notes` | `skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `list-and-sort-typed-notes` | `skill` | `scenario_compliance` | 5.000 | 10 | higher is better |
| `list-and-sort-typed-notes` | `skill` | `safety` | 5.000 | 10 | higher is better |
| `list-and-sort-typed-notes` | `skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `list-and-sort-typed-notes` | `skill` | `tool_efficiency` | 4.900 | 10 | higher is better |
| `list-and-sort-typed-notes` | `skill` | `resource_efficiency` | 4.900 | 10 | higher is better |
| `list-and-sort-typed-notes` | `skill` | `wall_time_seconds` | 54.647 | 10 | lower is better |
| `list-and-sort-typed-notes` | `skill` | `n_input_tokens` | 49511.900 | 10 | lower is better |
| `list-and-sort-typed-notes` | `skill` | `n_cache_tokens` | 40371.200 | 10 | lower is better |
| `list-and-sort-typed-notes` | `skill` | `n_output_tokens` | 346.500 | 10 | lower is better |
| `list-and-sort-typed-notes` | `skill` | `cost_usd` | 0.003051 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `task_correctness` | 3.400 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `scenario_compliance` | 3.500 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `safety` | 5.000 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `evidence_quality` | 3.800 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `tool_efficiency` | 1.500 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `resource_efficiency` | 1.400 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `wall_time_seconds` | 80.500 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `n_input_tokens` | 123809.100 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `n_cache_tokens` | 97945.600 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `n_output_tokens` | 1473.800 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `no-skill` | `cost_usd` | 0.008900 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `skill_compliance` | 5.000 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `scenario_compliance` | 5.000 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `safety` | 5.000 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `tool_efficiency` | 5.000 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `resource_efficiency` | 5.000 | 10 | higher is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `wall_time_seconds` | 60.368 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `n_input_tokens` | 48385.500 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `n_cache_tokens` | 39168.000 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `n_output_tokens` | 613.800 | 10 | lower is better |
| `query-structured-metadata-without-scanning-files` | `skill` | `cost_usd` | 0.003363 | 10 | lower is better |
| `read-one-note-with-parent-context` | `no-skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `no-skill` | `scenario_compliance` | 4.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `no-skill` | `safety` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `no-skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `no-skill` | `tool_efficiency` | 2.800 | 10 | higher is better |
| `read-one-note-with-parent-context` | `no-skill` | `resource_efficiency` | 3.600 | 10 | higher is better |
| `read-one-note-with-parent-context` | `no-skill` | `wall_time_seconds` | 55.032 | 10 | lower is better |
| `read-one-note-with-parent-context` | `no-skill` | `n_input_tokens` | 42763.500 | 10 | lower is better |
| `read-one-note-with-parent-context` | `no-skill` | `n_cache_tokens` | 32665.600 | 10 | lower is better |
| `read-one-note-with-parent-context` | `no-skill` | `n_output_tokens` | 333.500 | 10 | lower is better |
| `read-one-note-with-parent-context` | `no-skill` | `cost_usd` | 0.003073 | 10 | lower is better |
| `read-one-note-with-parent-context` | `skill` | `skill_compliance` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `skill` | `scenario_compliance` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `skill` | `safety` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `skill` | `tool_efficiency` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `skill` | `resource_efficiency` | 5.000 | 10 | higher is better |
| `read-one-note-with-parent-context` | `skill` | `wall_time_seconds` | 54.603 | 10 | lower is better |
| `read-one-note-with-parent-context` | `skill` | `n_input_tokens` | 47828.600 | 10 | lower is better |
| `read-one-note-with-parent-context` | `skill` | `n_cache_tokens` | 40396.800 | 10 | lower is better |
| `read-one-note-with-parent-context` | `skill` | `n_output_tokens` | 352.500 | 10 | lower is better |
| `read-one-note-with-parent-context` | `skill` | `cost_usd` | 0.002717 | 10 | lower is better |
| `summarize-one-topic` | `no-skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `no-skill` | `scenario_compliance` | 3.400 | 10 | higher is better |
| `summarize-one-topic` | `no-skill` | `safety` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `no-skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `no-skill` | `tool_efficiency` | 1.800 | 10 | higher is better |
| `summarize-one-topic` | `no-skill` | `resource_efficiency` | 1.700 | 10 | higher is better |
| `summarize-one-topic` | `no-skill` | `wall_time_seconds` | 62.725 | 10 | lower is better |
| `summarize-one-topic` | `no-skill` | `n_input_tokens` | 81840.400 | 10 | lower is better |
| `summarize-one-topic` | `no-skill` | `n_cache_tokens` | 70092.800 | 10 | lower is better |
| `summarize-one-topic` | `no-skill` | `n_output_tokens` | 729.600 | 10 | lower is better |
| `summarize-one-topic` | `no-skill` | `cost_usd` | 0.004627 | 10 | lower is better |
| `summarize-one-topic` | `skill` | `skill_compliance` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `skill` | `task_correctness` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `skill` | `scenario_compliance` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `skill` | `safety` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `skill` | `evidence_quality` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `skill` | `tool_efficiency` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `skill` | `resource_efficiency` | 5.000 | 10 | higher is better |
| `summarize-one-topic` | `skill` | `wall_time_seconds` | 53.471 | 10 | lower is better |
| `summarize-one-topic` | `skill` | `n_input_tokens` | 47727.000 | 10 | lower is better |
| `summarize-one-topic` | `skill` | `n_cache_tokens` | 39372.800 | 10 | lower is better |
| `summarize-one-topic` | `skill` | `n_output_tokens` | 336.100 | 10 | lower is better |
| `summarize-one-topic` | `skill` | `cost_usd` | 0.002862 | 10 | lower is better |

### Common-valid paired cohorts and treatment-minus-control deltas

All deltas are treatment minus control. Positive score deltas are better; negative resource deltas are better.

| Group | Measure | Mean delta | n |
|---|---|---:|---:|
| `overall:overall` | `task_correctness` | 0.617 | 60 |
| `overall:overall` | `scenario_compliance` | 1.083 | 60 |
| `overall:overall` | `safety` | 0.000 | 60 |
| `overall:overall` | `evidence_quality` | 0.300 | 60 |
| `overall:overall` | `tool_efficiency` | 2.800 | 60 |
| `overall:overall` | `resource_efficiency` | 2.667 | 60 |
| `overall:overall` | `wall_time_seconds` | -7.954 | 60 |
| `overall:overall` | `n_input_tokens` | -26668.850 | 60 |
| `overall:overall` | `n_cache_tokens` | -20326.400 | 60 |
| `overall:overall` | `n_output_tokens` | -345.783 | 60 |
| `overall:overall` | `cost_usd` | -0.002090 | 60 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `task_correctness` | 0.000 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `scenario_compliance` | 0.000 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `safety` | 0.000 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `evidence_quality` | 0.000 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `tool_efficiency` | 0.600 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `resource_efficiency` | 0.600 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `wall_time_seconds` | 0.505 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `n_input_tokens` | 13376.400 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `n_cache_tokens` | 10470.400 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `n_output_tokens` | 26.700 | 10 |
| `scenario:ambiguous-discovery-with-one-follow-up` | `cost_usd` | 0.000823 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `task_correctness` | 0.000 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `scenario_compliance` | 0.900 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `safety` | 0.000 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `evidence_quality` | 0.000 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `tool_efficiency` | 3.700 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `resource_efficiency` | 3.600 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `wall_time_seconds` | -10.628 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `n_input_tokens` | -42554.400 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `n_cache_tokens` | -27443.200 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `n_output_tokens` | -497.400 | 10 |
| `scenario:discover-and-retrieve-bounded-multi-hop-context` | `cost_usd` | -0.004168 | 10 |
| `scenario:list-and-sort-typed-notes` | `task_correctness` | 2.100 | 10 |
| `scenario:list-and-sort-typed-notes` | `scenario_compliance` | 1.500 | 10 |
| `scenario:list-and-sort-typed-notes` | `safety` | 0.000 | 10 |
| `scenario:list-and-sort-typed-notes` | `evidence_quality` | 0.600 | 10 |
| `scenario:list-and-sort-typed-notes` | `tool_efficiency` | 3.600 | 10 |
| `scenario:list-and-sort-typed-notes` | `resource_efficiency` | 3.500 | 10 |
| `scenario:list-and-sort-typed-notes` | `wall_time_seconds` | -7.786 | 10 |
| `scenario:list-and-sort-typed-notes` | `n_input_tokens` | -26363.200 | 10 |
| `scenario:list-and-sort-typed-notes` | `n_cache_tokens` | -23219.200 | 10 |
| `scenario:list-and-sort-typed-notes` | `n_output_tokens` | -369.500 | 10 |
| `scenario:list-and-sort-typed-notes` | `cost_usd` | -0.001537 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `task_correctness` | 1.600 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `scenario_compliance` | 1.500 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `safety` | 0.000 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `evidence_quality` | 1.200 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `tool_efficiency` | 3.500 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `resource_efficiency` | 3.600 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `wall_time_seconds` | -20.132 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `n_input_tokens` | -75423.600 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `n_cache_tokens` | -58777.600 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `n_output_tokens` | -860.000 | 10 |
| `scenario:query-structured-metadata-without-scanning-files` | `cost_usd` | -0.005537 | 10 |
| `scenario:read-one-note-with-parent-context` | `task_correctness` | 0.000 | 10 |
| `scenario:read-one-note-with-parent-context` | `scenario_compliance` | 1.000 | 10 |
| `scenario:read-one-note-with-parent-context` | `safety` | 0.000 | 10 |
| `scenario:read-one-note-with-parent-context` | `evidence_quality` | 0.000 | 10 |
| `scenario:read-one-note-with-parent-context` | `tool_efficiency` | 2.200 | 10 |
| `scenario:read-one-note-with-parent-context` | `resource_efficiency` | 1.400 | 10 |
| `scenario:read-one-note-with-parent-context` | `wall_time_seconds` | -0.430 | 10 |
| `scenario:read-one-note-with-parent-context` | `n_input_tokens` | 5065.100 | 10 |
| `scenario:read-one-note-with-parent-context` | `n_cache_tokens` | 7731.200 | 10 |
| `scenario:read-one-note-with-parent-context` | `n_output_tokens` | 19.000 | 10 |
| `scenario:read-one-note-with-parent-context` | `cost_usd` | -0.000356 | 10 |
| `scenario:summarize-one-topic` | `task_correctness` | 0.000 | 10 |
| `scenario:summarize-one-topic` | `scenario_compliance` | 1.600 | 10 |
| `scenario:summarize-one-topic` | `safety` | 0.000 | 10 |
| `scenario:summarize-one-topic` | `evidence_quality` | 0.000 | 10 |
| `scenario:summarize-one-topic` | `tool_efficiency` | 3.200 | 10 |
| `scenario:summarize-one-topic` | `resource_efficiency` | 3.300 | 10 |
| `scenario:summarize-one-topic` | `wall_time_seconds` | -9.254 | 10 |
| `scenario:summarize-one-topic` | `n_input_tokens` | -34113.400 | 10 |
| `scenario:summarize-one-topic` | `n_cache_tokens` | -30720.000 | 10 |
| `scenario:summarize-one-topic` | `n_output_tokens` | -393.500 | 10 |
| `scenario:summarize-one-topic` | `cost_usd` | -0.001765 | 10 |

## Failures and reliability

### Deterministic benchmark failures

- `no-skill/list-and-sort-typed-notes/3`: response values missing or out of order
- `no-skill/list-and-sort-typed-notes/4`: response values missing or out of order
- `no-skill/list-and-sort-typed-notes/5`: response values missing or out of order
- `no-skill/list-and-sort-typed-notes/7`: response values missing or out of order
- `no-skill/list-and-sort-typed-notes/8`: response values missing or out of order
- `no-skill/list-and-sort-typed-notes/9`: response values missing or out of order
- `no-skill/list-and-sort-typed-notes/10`: response values missing or out of order
- `no-skill/query-structured-metadata-without-scanning-files/4`: response missing semantic patterns \[&#x27;(?i)(?&lt;!\[A-Za-z0-9_-\])bge(?!\[A-Za-z0-9_-\])&#x27;, &#x27;(?i)(?&lt;!\[A-Za-z0-9_-\])power-dynamics(?!\[A-Za-z0-9_-\])&#x27;\]; response missing semantic patterns \[&#x27;(?i)(?&lt;!\[A-Za-z0-9_-\])virtue-across-centuries(?!\[A-Za-z0-9_-\])&#x27;, &#x27;(?i)(?&lt;!\[A-Za-z0-9_-\])moral-systems(?!\[A-Za-z0-9_-\])&#x27;\]
- `no-skill/query-structured-metadata-without-scanning-files/8`: response missing semantic patterns \[&#x27;(?i)(?&lt;!\[A-Za-z0-9_-\])virtue-across-centuries(?!\[A-Za-z0-9_-\])&#x27;\]
- `no-skill/query-structured-metadata-without-scanning-files/10`: response missing semantic patterns \[&#x27;(?i)(?&lt;!\[A-Za-z0-9_-\])virtue-across-centuries(?!\[A-Za-z0-9_-\])&#x27;\]

### Invalid or unavailable evidence

None.

### Below-threshold judge scores

- `no-skill/ambiguous-discovery-with-one-follow-up/2`: `tool_efficiency` `3.000/4`; `resource_efficiency` `3.000/4`.
- `no-skill/ambiguous-discovery-with-one-follow-up/10`: `tool_efficiency` `3.000/4`; `resource_efficiency` `3.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/1`: `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/2`: `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/3`: `scenario_compliance` `3.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/4`: `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/5`: `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/6`: `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/7`: `scenario_compliance` `4.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/8`: `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/9`: `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/discover-and-retrieve-bounded-multi-hop-context/10`: `scenario_compliance` `3.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/list-and-sort-typed-notes/1`: `tool_efficiency` `2.000/4`; `resource_efficiency` `3.000/4`.
- `no-skill/list-and-sort-typed-notes/2`: `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/list-and-sort-typed-notes/3`: `task_correctness` `2.000/5`; `scenario_compliance` `2.000/5`; `evidence_quality` `4.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/list-and-sort-typed-notes/4`: `task_correctness` `2.000/5`; `scenario_compliance` `3.000/5`; `evidence_quality` `3.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/list-and-sort-typed-notes/5`: `task_correctness` `2.000/5`; `scenario_compliance` `3.000/5`; `evidence_quality` `4.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/list-and-sort-typed-notes/6`: `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/list-and-sort-typed-notes/7`: `task_correctness` `2.000/5`; `scenario_compliance` `3.000/5`; `evidence_quality` `4.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/list-and-sort-typed-notes/8`: `task_correctness` `2.000/5`; `scenario_compliance` `3.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/list-and-sort-typed-notes/9`: `task_correctness` `2.000/5`; `scenario_compliance` `3.000/5`; `evidence_quality` `4.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/list-and-sort-typed-notes/10`: `task_correctness` `2.000/5`; `scenario_compliance` `3.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/1`: `evidence_quality` `4.000/5`; `tool_efficiency` `3.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/2`: `task_correctness` `2.000/5`; `scenario_compliance` `2.000/5`; `evidence_quality` `2.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/3`: `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/4`: `task_correctness` `2.000/5`; `scenario_compliance` `3.000/5`; `evidence_quality` `2.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/5`: `task_correctness` `2.000/5`; `scenario_compliance` `3.000/5`; `evidence_quality` `3.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/6`: `task_correctness` `2.000/5`; `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/7`: `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/8`: `task_correctness` `3.000/5`; `scenario_compliance` `3.000/5`; `evidence_quality` `4.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/9`: `scenario_compliance` `3.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/query-structured-metadata-without-scanning-files/10`: `task_correctness` `3.000/5`; `scenario_compliance` `3.000/5`; `evidence_quality` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/read-one-note-with-parent-context/1`: `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/read-one-note-with-parent-context/2`: `scenario_compliance` `4.000/5`; `tool_efficiency` `3.000/4`.
- `no-skill/read-one-note-with-parent-context/3`: `scenario_compliance` `4.000/5`; `tool_efficiency` `3.000/4`.
- `no-skill/read-one-note-with-parent-context/4`: `scenario_compliance` `4.000/5`; `tool_efficiency` `3.000/4`.
- `no-skill/read-one-note-with-parent-context/5`: `scenario_compliance` `4.000/5`; `tool_efficiency` `3.000/4`.
- `no-skill/read-one-note-with-parent-context/6`: `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/read-one-note-with-parent-context/7`: `scenario_compliance` `4.000/5`; `tool_efficiency` `3.000/4`.
- `no-skill/read-one-note-with-parent-context/8`: `scenario_compliance` `4.000/5`; `tool_efficiency` `3.000/4`.
- `no-skill/read-one-note-with-parent-context/9`: `scenario_compliance` `4.000/5`; `tool_efficiency` `3.000/4`.
- `no-skill/read-one-note-with-parent-context/10`: `scenario_compliance` `4.000/5`; `tool_efficiency` `3.000/4`.
- `no-skill/summarize-one-topic/1`: `scenario_compliance` `3.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/summarize-one-topic/2`: `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/summarize-one-topic/3`: `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/summarize-one-topic/4`: `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/summarize-one-topic/5`: `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/summarize-one-topic/6`: `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/summarize-one-topic/7`: `scenario_compliance` `3.000/5`; `tool_efficiency` `1.000/4`; `resource_efficiency` `1.000/4`.
- `no-skill/summarize-one-topic/8`: `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/summarize-one-topic/9`: `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.
- `no-skill/summarize-one-topic/10`: `scenario_compliance` `3.000/5`; `tool_efficiency` `2.000/4`; `resource_efficiency` `2.000/4`.

### Reliability and missingness

- Planned / observed / valid cells: `120` / `120` / `120`.
- Invalid cells: `0`.
- Deterministic failures by arm: `{"no-skill": 10, "skill": 0}`.
- Deterministic outcome is the verifier's mechanical/postcondition gate; semantic task quality remains represented by the independently judged dimensions.
- Common-valid pairs: `60` / `60`.
- Excluded pairs: `[]`.

## Timing

- Available-valid summed cell-seconds: `7353.587`.
- Common-valid summed cell-seconds: `7353.587`.
- Pipeline elapsed seconds: `4476.871`.

Summed cell-seconds measure aggregate worker trial time; pipeline elapsed time measures end-to-end execution including judging and concurrency.

## Audit appendix

Cell-level evidence is retained in the source bundle's sealed publishable-evidence scope but is not included in this publication. The seal covers the evidence consumed by bundle validation and report generation, not transient raw Harbor operational files. Complete machine-readable statistics remain available in the sealed summary JSON.

## Sanitized device telemetry

<details>
<summary>Complete sanitized device telemetry</summary>

```json
{
  "cpu_percent_max": 100.0,
  "disk_read_bytes_per_second_max": 202721763.77952754,
  "disk_read_bytes_total": 20645842944,
  "disk_scope": "physical-block-devices",
  "disk_write_bytes_per_second_max": 37623470.78705939,
  "disk_write_bytes_total": 8729440256,
  "docker_oom_events": 0,
  "load1_max": 3.61,
  "logical_cpus": 2,
  "mem_available_bytes_min": 845520896,
  "network_rx_bytes_per_second_max": 41553539.89231522,
  "network_rx_bytes_total": 5826413305,
  "network_scope": "default-route-interfaces",
  "network_tx_bytes_per_second_max": 787504.9164208457,
  "network_tx_bytes_total": 154725916,
  "rootfs_free_bytes_min": 5860036608,
  "rootfs_scope": "root-filesystem",
  "rootfs_used_bytes_max": 40408367104,
  "running_containers_max": 8,
  "sample_count": 2182,
  "sampling_errors": 0,
  "schema_version": 2,
  "scope": "whole-host",
  "swap_free_bytes_min": 7490129920,
  "terminal_status": "completed",
  "total_memory_bytes": 4041781248,
  "total_swap_bytes": 9091141632
}
```

</details>

The report is derived from the bundled, sealed machine-readable evidence. Device telemetry is schema-constrained to numeric capacity and load measurements; hostnames, usernames, paths, environment variables, command lines, network identifiers, container names, labels, and credential material are not accepted.
