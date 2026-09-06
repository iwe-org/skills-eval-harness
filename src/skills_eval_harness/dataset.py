"""Generate self-contained Harbor v1.1 task datasets."""
from __future__ import annotations

import json
import inspect
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import cast

from harbor.models.task.config import TaskConfig

from .hashing import atomic_write, canonical_json, sha256_file, sha256_tree
from .models import HarnessConfig, Suite, load_yaml
from .postconditions import CATALOG_ASSERTIONS, validate_catalog_assertion

POSTCONDITIONS_SOURCE = Path(__file__).with_name("postconditions.py")
ATTESTATIONS_SOURCE = Path(__file__).with_name("attestations.py")

DEFAULT_HARD_TOOL_CALL_LIMIT = 8
def _is_bounded_skill_load(action: str) -> bool:
    normalized = action.replace("});\ntext(r.output);", "}); text(r.output);")
    return (
        "sed -n" in normalized
        and "/root/.agents/skills/" in normalized
        and "SKILL.md" in normalized
        and "&&" not in normalized
        and "||" not in normalized
    )

_SKILL_LOAD_FUNCTION = inspect.getsource(_is_bounded_skill_load).replace(
    "def _is_bounded_skill_load(action: str) -> bool:", "def skill_load(action):", 1
)

VERIFIER_TEMPLATE = r'''#!/usr/bin/env python3
import hashlib, json, os
from pathlib import Path
from postconditions import evaluate_postconditions
from attestations import fallback_attestation

def tree(root):
    rows=[]
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if {".git","__pycache__",".DS_Store"} & set(path.relative_to(root).parts): continue
        if path.is_symlink():
            target=path.resolve()
            if not target.is_relative_to(root.resolve()):
                raise ValueError(f"escaping symlink: {path}")
        if path.is_file():
            rows.append({"path":path.relative_to(root).as_posix(),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size})
    return rows

trajectory=Path("/logs/agent/trajectory.json")
if not trajectory.is_file():
    raise ValueError("missing declared agent trajectory")
document=json.loads(trajectory.read_text(encoding="utf-8"))
if not isinstance(document,dict) or not isinstance(document.get("steps"),list):
    raise ValueError("malformed ATIF trajectory")
workspace=Path("/workspace")
manifest=tree(workspace)
before=json.loads(Path("/tests/before-tree.json").read_text(encoding="utf-8"))
policy=json.loads(Path("/tests/policy.json").read_text(encoding="utf-8"))
oracle=json.loads(Path("/tests/oracle.json").read_text(encoding="utf-8"))
postconditions=json.loads(Path("/tests/postconditions.json").read_text(encoding="utf-8"))
def collect_tools(value):
    if isinstance(value,dict):
        own=value.get("tool_calls",[]) if isinstance(value.get("tool_calls"),list) else []
        nested=[]
        for key,item in value.items():
            if key != "tool_calls": nested.extend(collect_tools(item))
        return own+nested
    if isinstance(value,list):
        return [call for item in value for call in collect_tools(item)]
    return []
__SKILL_LOAD_FUNCTION__
def is_skill_load(call):
    if not isinstance(call,dict) or call.get("function_name") != "exec": return False
    arguments=call.get("arguments")
    return isinstance(arguments,dict) and set(arguments)=={"input"} and isinstance(arguments["input"],str) and skill_load(arguments["input"])
def confounded_skill_load(call):
    if not isinstance(call,dict) or call.get("function_name") != "exec" or is_skill_load(call): return False
    arguments=call.get("arguments")
    action=arguments.get("input") if isinstance(arguments,dict) else None
    if not isinstance(action,str): return False
    for separator in ("&&",";","\n"):
        setup, found, task = action.partition(separator)
        if found and task.strip() and skill_load(setup.strip()): return True
    return False
def task_output_bytes(document):
    return sum(
        len(json.dumps(step.get("observation"),ensure_ascii=False,sort_keys=True).encode("utf-8"))
        for step in document["steps"]
        if isinstance(step,dict) and isinstance(step.get("tool_calls"),list) and any(not is_skill_load(call) for call in step["tool_calls"])
    )
all_tool_calls=collect_tools(document)
setup_tool_calls=sum(is_skill_load(call) for call in all_tool_calls)
tool_calls=len(all_tool_calls)-setup_tool_calls
task_tool_output_bytes=task_output_bytes(document)
measurement_confounded=any(confounded_skill_load(call) for call in all_tool_calls)
unchanged=manifest==before
failures=[]
if policy["read_only"] and not unchanged: failures.append("read-only scenario modified workspace")
if policy["mutation_expected"] and unchanged: failures.append("mutation scenario left workspace unchanged")
hard_max=policy.get("hard_max_task_tool_calls")
if hard_max is not None and tool_calls>hard_max: failures.append("hard tool-call maximum exceeded")
messages=[step["message"] for step in document["steps"] if isinstance(step,dict) and step.get("source")=="agent" and isinstance(step.get("message"),str) and step["message"].strip()]
if not messages: raise ValueError("trajectory has no final assistant response")
attestation_specs=[item for item in postconditions if item.get("type")=="targeted_fallback_read"]
postconditions=[item for item in postconditions if item.get("type")!="targeted_fallback_read"]
attestations=[]
for spec in attestation_specs:
    attestation=fallback_attestation(document,spec["path"])
    attestations.append(attestation)
    if attestation.get("protocol")!="fallback-attestation-v4": failures.append("fallback attestation protocol mismatch")
    if not attestation["runtime_attempt_observed"]: failures.append("fallback runtime attempt not observed exactly once")
    if not attestation["runtime_unavailable_observed"]: failures.append("fallback runtime unavailable result not observed")
    if not attestation["targeted_fallback_observed"]: failures.append("exact targeted fallback read not observed")
    if attestation["unrelated_post_failure_tool_call_observed"]: failures.append("unrelated post-failure tool call observed")
Path("/logs/verifier/fallback-attestation.json").write_text(json.dumps({"attestations":attestations},sort_keys=True,separators=(",",":")))
postcondition_failures=evaluate_postconditions(root=workspace,before_rows=before,response=messages[-1],specs=postconditions)
failures.extend(postcondition_failures)
before_by_path={row["path"]:row for row in before}
after_by_path={row["path"]:row for row in manifest}
changed=[]
text_budget=6000
for path in sorted(set(before_by_path)|set(after_by_path)):
    old=before_by_path.get(path)
    new=after_by_path.get(path)
    if old==new: continue
    item={"path":path,"before":old,"after":new}
    target=workspace/path
    if new is not None and target.is_file() and text_budget:
        payload=target.read_bytes()
        try:
            text=payload.decode("utf-8")
        except UnicodeDecodeError:
            text=None
        if text is not None:
            excerpt=text[:min(4096,text_budget)]
            item["text_excerpt"]=excerpt
            item["text_truncated"]=len(excerpt)<len(text)
            text_budget-=len(excerpt)
    changed.append(item)
workspace_payload={"workspace":manifest,"baseline_unchanged":unchanged,"changes":changed}
mechanical_payload={"baseline_unchanged":unchanged,"tool_calls":tool_calls,"setup_tool_calls":setup_tool_calls,"total_tool_calls":len(all_tool_calls),"task_tool_output_bytes":task_tool_output_bytes,"measurement_confounded":measurement_confounded,"failures":failures,"trajectory_sha256":hashlib.sha256(trajectory.read_bytes()).hexdigest()}
Path("/logs/verifier/oracle.json").write_text(json.dumps(oracle,sort_keys=True,separators=(",",":")),encoding="utf-8")
Path("/logs/verifier/workspace-manifest.json").write_text(json.dumps(workspace_payload,sort_keys=True,separators=(",",":")),encoding="utf-8")
Path("/logs/verifier/mechanical.json").write_text(json.dumps(mechanical_payload,sort_keys=True,separators=(",",":")),encoding="utf-8")
Path("/logs/verifier/postconditions.json").write_text(json.dumps({"failures":postcondition_failures,"passed":not postcondition_failures},sort_keys=True,separators=(",",":")),encoding="utf-8")
Path("/logs/verifier/reward.json").write_text(json.dumps({"infrastructure":0.0 if failures else 1.0}),encoding="utf-8")
'''
VERIFIER = VERIFIER_TEMPLATE.replace("__SKILL_LOAD_FUNCTION__", _SKILL_LOAD_FUNCTION)


TEST_SH = "#!/bin/sh\nset -eu\npython3 /tests/verify.py\n"


def agent_dockerfile(config: HarnessConfig) -> str:
    return (
        f"FROM {config.container.agent_image}@{config.container.agent_image_id}\n"
        "COPY payload/ /\n"
        "WORKDIR /workspace\n"
    )

def _copy(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination) if destination.is_dir() else destination.unlink()
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=False, ignore=shutil.ignore_patterns(".git"))
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)


def _materialize_runtime(source: Path, destination: Path, mode: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if mode == "available":
        _copy(source, destination)
    elif mode == "unavailable":
        destination.write_text("#!/bin/sh\nprintf '%s\\n' 'iwe: unavailable in this scenario' >&2\nexit 127\n", encoding="utf-8")
    else:
        raise ValueError(f"unknown runtime mode: {mode!r}")
    destination.chmod(0o755)

def _tree_manifest(root: Path) -> list[dict[str, object]]:
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and ".git" not in path.relative_to(root).parts
    ]


def _runtime_relationships(
    workspace: Path, runtime: Path, terms: set[str]
) -> dict[str, dict[str, list[str]]]:
    """Read exact-key relationships from the pinned IWE runtime."""
    library = workspace
    config = workspace / ".iwe/config.toml"
    if config.is_file():
        configured = tomllib.loads(config.read_text(encoding="utf-8")).get("library", {}).get("path", ".")
        if not isinstance(configured, str):
            raise ValueError("IWE library path must be a string")
        candidate = (workspace / configured).resolve()
        if not candidate.is_relative_to(workspace.resolve()):
            raise ValueError("IWE library path escapes fixture root")
        library = candidate
    by_key: dict[str, list[Path]] = {}
    for path in sorted(library.rglob("*.md"), key=lambda item: item.as_posix()):
        by_key.setdefault(path.stem.lower(), []).append(path)
    duplicate = sorted(key for key, paths in by_key.items() if key in terms and len(paths) != 1)
    if duplicate:
        raise ValueError(f"duplicate IWE keys: {duplicate}")
    keys = sorted(terms & by_key.keys())
    if not keys:
        return {}
    if len(keys) > 8:
        raise ValueError("semantic oracle relationship query exceeds eight exact keys")
    command = [str(runtime), "find"]
    for key in keys:
        command.extend(("--key", key))
    command.extend((
        "--limit", str(len(keys)),
        "--add-fields", "references=$references,referencedBy=$referencedBy,includes=$includes,includedBy=$includedBy",
        "--format", "json",
    ))
    result = subprocess.run(
        command,
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    rows = json.loads(result.stdout)
    if not isinstance(rows, list) or len(rows) != len(keys):
        raise ValueError("IWE relationship query returned an unexpected row count")
    relationships: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("key") not in keys or row["key"] in relationships:
            raise ValueError("IWE relationship query returned an invalid key")
        directions: dict[str, list[str]] = {}
        for direction in ("references", "referencedBy", "includes", "includedBy"):
            values = row.get(direction)
            if not isinstance(values, list) or any(
                not isinstance(value, dict) or not isinstance(value.get("key"), str) for value in values
            ):
                raise ValueError("IWE relationship query returned an invalid relation")
            directions[direction] = sorted({value["key"] for value in values})
        relationships[row["key"]] = directions
    if set(relationships) != set(keys):
        raise ValueError("IWE relationship query omitted an exact key")
    return relationships


def _semantic_oracle(workspace: Path, scenario: dict, runtime: Path) -> dict:
    terms = {
        value.lower()
        for value in re.findall(r"[A-Za-z0-9_-]{4,}", scenario["request"])
    }
    candidates: list[tuple[int, str, str, str]] = []
    for path in sorted(workspace.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or ".git" in path.relative_to(workspace).parts:
            continue
        payload = path.read_bytes()
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(workspace).as_posix()
        haystack = f"{relative}\n{text}".lower()
        score = sum(4 if term in relative.lower() else 1 for term in terms if term in haystack)
        candidates.append((score, relative, sha256_file(path), text))
    excerpts = []
    budget = 5500
    ranked = sorted(candidates, key=lambda item: (-item[0], item[1]))
    prioritized = []
    for term in sorted(terms):
        path_matches = [
            item
            for item in ranked
            if term in {part.lower() for part in re.findall(r"[A-Za-z0-9]+", item[1])}
        ]
        if path_matches and path_matches[0] not in prioritized:
            prioritized.append(path_matches[0])
    ranked = prioritized + [item for item in ranked if item not in prioritized]
    use_zero_score = not any(item[0] > 0 for item in ranked)
    for score, relative, digest, text in ranked:
        if len(excerpts) == 4:
            break
        if score == 0 and not use_zero_score:
            continue
        excerpt = text[:1600]
        encoded = excerpt.encode("utf-8")
        if len(encoded) > budget:
            continue
        excerpts.append({"path": relative, "sha256": digest, "text": excerpt})
        budget -= len(encoded)
    if not excerpts:
        raise ValueError(f"scenario {scenario['id']} has no fixture-derived semantic oracle evidence")
    return {
        "procedure": scenario["procedure"],
        "excellent": scenario["excellent"],
        "source_excerpts": excerpts,
        "relationships": _runtime_relationships(workspace, runtime, terms),
    }

def _companion_assertions(path: Path) -> dict[str, list[dict]]:
    source = path.parent.parent / "postconditions" / path.name
    document = cast(dict, load_yaml(source))
    items = document.get("scenarios")
    if document.get("schema_version") != 1 or not isinstance(items, list):
        raise ValueError("postcondition catalog must use schema_version 1")
    return {item["id"]: item["assertions"] for item in items}


def scenario_map(path: Path) -> dict[str, dict]:
    document = load_yaml(path)
    if document.get("schema_version") != 2 or not isinstance(document.get("scenarios"), list):
        raise ValueError("scenario catalog must use schema_version 2")
    scenarios = {item["id"]: item for item in document["scenarios"]}
    if len(scenarios) != len(document["scenarios"]):
        raise ValueError("duplicate scenario IDs")
    embedded = ["postconditions" in scenario for scenario in scenarios.values()]
    if any(embedded) and not all(embedded):
        raise ValueError("scenario catalog mixes embedded and companion postconditions")
    if all(embedded):
        assertions = {scenario_id: scenario["postconditions"] for scenario_id, scenario in scenarios.items()}
    else:
        assertions = _companion_assertions(path)
    if set(assertions) != set(scenarios):
        raise ValueError("postcondition catalog scenario IDs differ from scenario catalog")
    for scenario_id, scenario in scenarios.items():
        specs = assertions[scenario_id]
        if not isinstance(specs, list) or not specs:
            raise ValueError(f"scenario {scenario_id} has no deterministic postconditions")
        for spec in specs:
            if not isinstance(spec, dict) or spec.get("type") not in CATALOG_ASSERTIONS:
                raise ValueError(f"scenario {scenario_id} has an unknown postcondition")
            validate_catalog_assertion(spec)
        scenario["postconditions"] = specs
    return scenarios

def task_toml(*, name: str, fixture: str, config: HarnessConfig, agent: str) -> str:
    c = config.container
    return f'''schema_version = "1.4"
artifacts = ["/workspace", "/logs/agent/trajectory.json"]

[task]
name = "iwe/{name}"
description = "IWE skill evaluation: {name}"
authors = []

[metadata]
fixture = "{fixture}"
harness_protocol = "iwe-harbor-v1"

[agent]
timeout_sec = {float(config.execution.timeout_seconds)}
network_mode = "{c.network_mode}"
allowed_hosts = {json.dumps(list(c.agent_hosts[agent]))}

[verifier]
timeout_sec = 300.0
environment_mode = "separate"

[environment]
build_timeout_sec = 600.0
cpus = {c.cpus}
memory_mb = {c.memory_mb}
storage_mb = {c.storage_mb}
gpus = 0
network_mode = "public"
mcp_servers = []

[verifier.environment]
build_timeout_sec = 600.0
cpus = {c.cpus}
memory_mb = {c.memory_mb}
storage_mb = {c.storage_mb}
gpus = 0
network_mode = "{c.verifier_network_mode}"
mcp_servers = []
'''

def generate_dataset(*, root: Path, suite: Suite, config: HarnessConfig, catalog_path: Path, fixture_roots: dict[str, Path], runtime: Path, arm: str, agent: str = "codex", samples: int = 1, agents_template: bytes | None = None) -> Path:
    if arm not in {item.id for item in suite.arms}:
        raise ValueError(f"unknown arm {arm!r}")
    if agent not in config.agents or samples < 1:
        raise ValueError("unknown agent or invalid sample count")
    scenarios = scenario_map(catalog_path)
    missing = sorted(set(suite.scenarios) - set(scenarios))
    if missing:
        raise ValueError(f"suite references unknown scenarios: {missing}")
    output = root / suite.id / arm
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for scenario_id in suite.scenarios:
        scenario = scenarios[scenario_id]
        fixture_name = scenario["fixture"]
        fixture_root = fixture_roots.get(fixture_name)
        if fixture_root is None or not fixture_root.is_dir():
            raise ValueError(f"missing materialized fixture {fixture_name!r}")
        for sample in range(1, samples + 1):
            task_id = f"{scenario_id}--sample-{sample:03d}"
            task = output / task_id
            (task / "environment/payload/workspace").mkdir(parents=True)
            (task / "tests").mkdir(parents=True)
            _copy(fixture_root, task / "environment/payload/workspace")
            if agents_template is not None:
                (task / "environment/payload/workspace/AGENTS.md").write_bytes(agents_template)
            runtime_mode = str((scenario.get("runtime") or {}).get("mode", "available"))
            effective_runtime = task / "environment/payload/usr/local/bin/iwe"
            _materialize_runtime(runtime, effective_runtime, runtime_mode)
            image = config.container.image
            (task / "environment/Dockerfile").write_text(agent_dockerfile(config), encoding="utf-8")
            (task / "tests/Dockerfile").write_text(f"FROM {image}\nCOPY . /tests/\n", encoding="utf-8")
            (task / "tests/verify.py").write_text(VERIFIER, encoding="utf-8")
            _copy(POSTCONDITIONS_SOURCE, task / "tests/postconditions.py")
            _copy(ATTESTATIONS_SOURCE, task / "tests/attestations.py")
            (task / "tests/test.sh").write_text(TEST_SH, encoding="utf-8")
            (task / "tests/test.sh").chmod(0o755)
            write_capability = any(str(capability).startswith("write.") for capability in scenario.get("capabilities", []))
            runtime_policy = scenario.get("runtime") or {}
            efficiency = scenario.get("efficiency") or {}
            hard_max = runtime_policy.get("hard_max_task_tool_calls")
            if hard_max is None and efficiency.get("task_tool_calls"):
                hard_max = max(DEFAULT_HARD_TOOL_CALL_LIMIT, efficiency["task_tool_calls"][1])
            mutation_expected = bool(scenario.get("mutation_expected", write_capability))
            atomic_write(task / "tests/before-tree.json", canonical_json(_tree_manifest(task / "environment/payload/workspace")))
            atomic_write(
                task / "tests/policy.json",
                canonical_json({
                    "read_only": not mutation_expected,
                    "mutation_expected": mutation_expected,
                    "hard_max_task_tool_calls": hard_max,
                }),
            )
            atomic_write(
                task / "tests/oracle.json",
                canonical_json(_semantic_oracle(task / "environment/payload/workspace", scenario, runtime)),
            )
            atomic_write(task / "tests/postconditions.json", canonical_json(scenario.get("postconditions", [])))
            (task / "instruction.md").write_text(f"Work offline.\n\nRequest:\n{scenario['request']}\n", encoding="utf-8")
            text = task_toml(name=task_id, fixture=fixture_name, config=config, agent=agent)
            TaskConfig.model_validate_toml(text)
            (task / "task.toml").write_text(text, encoding="utf-8")
            manifest = {"protocol": "iwe-harbor-v2", "scenario_id": scenario_id, "sample": sample, "fixture_sha256": sha256_tree(fixture_root), "runtime_mode": runtime_mode, "runtime_sha256": sha256_file(runtime), "effective_runtime_sha256": sha256_file(effective_runtime)}
            atomic_write(task / "manifest.json", canonical_json(manifest))
    return output
