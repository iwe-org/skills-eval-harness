from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path
from typing import Callable, cast

import pytest
from harbor.models.task.config import TaskConfig

from skills_eval_harness.dataset import VERIFIER, _materialize_runtime, _runtime_relationships, generate_dataset, scenario_map
from skills_eval_harness.hashing import sha256_tree
from skills_eval_harness.models import load_config, load_suite

ROOT = Path(__file__).resolve().parents[1]


def fixture_inputs(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    runtime = tmp_path / "iwe"
    shutil.copy2("/bin/true", runtime)
    fixture = tmp_path / "pkm-demo"
    fixture.mkdir()
    (fixture / "note.md").write_text("# Demo\n", encoding="utf-8")
    (fixture / ".git").mkdir()
    (fixture / ".git/index").write_bytes(b"mutable metadata")
    return runtime, {"pkm-demo-core-read": fixture}


def test_graph_relationship_oracle_uses_pinned_runtime_and_whitelists_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = tmp_path / "graph"
    graph.mkdir()
    (tmp_path / ".iwe").mkdir()
    (tmp_path / ".iwe/config.toml").write_text('[library]\npath = "graph"\n', encoding="utf-8")
    (graph / "anchor.md").write_text("# Anchor\n", encoding="utf-8")
    calls: list[tuple[list[str], Path]] = []

    def fake_run(command, *, cwd, **kwargs):
        calls.append((command, cwd))
        return type("Result", (), {"stdout": json.dumps([{
            "key": "anchor",
            "title": "private",
            "content": "must not leak",
            "references": [{"key": "target", "title": "private", "sectionPath": []}],
            "referencedBy": [{"key": "source", "title": "private", "sectionPath": []}],
            "includes": [],
            "includedBy": [{"key": "parent", "title": "private", "sectionPath": []}],
        }])})()

    monkeypatch.setattr("skills_eval_harness.dataset.subprocess.run", fake_run)
    runtime = tmp_path / "iwe"
    assert _runtime_relationships(tmp_path, runtime, {"anchor", "unrelated"}) == {
        "anchor": {
            "references": ["target"],
            "referencedBy": ["source"],
            "includes": [],
            "includedBy": ["parent"],
        },
    }
    assert calls == [([
        str(runtime), "find", "--key", "anchor", "--limit", "1",
        "--add-fields", "references=$references,referencedBy=$referencedBy,includes=$includes,includedBy=$includedBy",
        "--format", "json",
    ], tmp_path)]


def test_generated_task_is_valid_separate_sandbox_and_pinned_image(tmp_path: Path) -> None:
    runtime, fixtures = fixture_inputs(tmp_path)
    suite = load_suite(ROOT / "evals/suites/skill-guidance-ab.yaml")
    dataset = generate_dataset(
        root=tmp_path / "datasets",
        suite=suite.model_copy(update={"scenarios": ("summarize-one-topic",)}),
        config=load_config(ROOT / "evals/config.yaml"),
        catalog_path=ROOT / "evals/scenarios/iwe.yaml",
        fixture_roots=fixtures,
        runtime=runtime,
        arm="skill",
        agent="codex",
    )
    task = dataset / "summarize-one-topic--sample-001"
    parsed = TaskConfig.model_validate_toml((task / "task.toml").read_text())
    assert parsed.verifier.environment_mode.value == "separate"
    assert parsed.environment.network_mode.value == "public"
    assert parsed.agent.network_mode.value == "allowlist"
    assert parsed.agent.allowed_hosts == list(load_config(ROOT / "evals/config.yaml").container.agent_hosts["codex"])
    assert parsed.verifier.environment.network_mode.value == "no-network"
    dockerfile = (task / "environment/Dockerfile").read_text()
    assert dockerfile.startswith(
        "FROM skills-eval-agent-toolchain:node22.23.2-codex0.147.0-claude2.1.233@"
        "sha256:778452e0c755ab2d7b5b79ebf3a1ed099cbc9942a7225717e7da108c3a5b3751\n"
    )
    assert "RUN " not in dockerfile
    toolchain = Path("docker/agent-toolchain.Dockerfile").read_text()
    assert "@openai/codex@0.147.0" in toolchain
    assert "@anthropic-ai/claude-code@2.1.233" in toolchain
    assert "node@22.23.2" in toolchain
    assert "@latest" not in toolchain
    verifier = (task / "tests/verify.py").read_text()
    assert "setup_tool_calls" in verifier
    assert "task_tool_output_bytes" in verifier
    assert 'policy["mutation_expected"] and unchanged' in verifier
    assert "mutation scenario left workspace unchanged" in verifier
    assert "def skill_load(action):" in verifier
    policy = json.loads((task / "tests/policy.json").read_text())
    assert policy["hard_max_task_tool_calls"] == 8
    assert policy["mutation_expected"] is False
    before = json.loads((task / "tests/before-tree.json").read_text())
    assert all(not row["path"].startswith(".git/") for row in before)
    assert not (task / "environment/payload/workspace/.git").exists()
    oracle_bytes = (task / "tests/oracle.json").read_bytes()
    oracle = json.loads(oracle_bytes)
    assert len(oracle_bytes) < 8_000
    assert oracle["source_excerpts"]
    for excerpt in oracle["source_excerpts"]:
        source = task / "environment/payload/workspace" / excerpt["path"]
        assert excerpt["text"] in source.read_text(encoding="utf-8")
        assert excerpt["sha256"] == next(row["sha256"] for row in before if row["path"] == excerpt["path"])
    assert "auth.json" not in sha256_tree(task)
    assert (task / "manifest.json").is_file()


def test_skill_load_classifier_excludes_only_the_bounded_skill_read() -> None:
    with_workdir = 'const r = await tools.exec_command({cmd:"sed -n \'1,240p\' /root/.agents/skills/iwe-v18/SKILL.md",workdir:"/workspace",yield_time_ms:10000,max_output_tokens:12000}); text(r.output);\n'
    without_workdir = 'const r = await tools.exec_command({cmd:"sed -n \'1,240p\' /root/.agents/skills/iwe-v18/SKILL.md",yield_time_ms:10000,max_output_tokens:20000}); text(r.output);\n'
    multiline = with_workdir.replace("}); text", "});\ntext")
    compound = with_workdir.replace("SKILL.md\"", "SKILL.md && iwe status\"")
    verifier_tree = ast.parse(VERIFIER)
    classifier = next(
        node for node in verifier_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "skill_load"
    )
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=[classifier], type_ignores=[]), "<verifier-classifier>", "exec"), namespace)
    classifier_fn = namespace["skill_load"]
    assert callable(classifier_fn)
    assert classifier_fn(with_workdir)
    assert classifier_fn(without_workdir)
    assert classifier_fn(multiline)
    assert not classifier_fn(compound)


def test_generated_verifier_measures_task_observation_bytes_and_flags_confounded_setup() -> None:
    tree = ast.parse(VERIFIER)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"skill_load", "is_skill_load", "confounded_skill_load", "task_output_bytes"}]
    namespace: dict[str, object] = {"json": json}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<verifier-bytes>", "exec"), namespace)
    task_call = {"function_name": "exec", "arguments": {"input": "read task"}}
    setup_call = {"function_name": "exec", "arguments": {"input": 'sed -n /root/.agents/skills/demo/SKILL.md'}}
    document = {"steps": [
        {"tool_calls": [task_call], "observation": {"result": "task output"}},
        {"tool_calls": [setup_call], "observation": {"result": "setup output"}},
    ]}
    expected = len(json.dumps(document["steps"][0]["observation"], ensure_ascii=False, sort_keys=True).encode("utf-8"))
    assert namespace["task_output_bytes"](document) == expected
    compound = {
        "function_name": "exec",
        "arguments": {"input": "sed -n '1,240p' /root/.agents/skills/demo/SKILL.md && inspect workspace"},
    }
    confounded = cast(Callable[[dict[str, object]], bool], namespace["confounded_skill_load"])
    assert confounded(compound)
    harmless = {
        "function_name": "exec",
        "arguments": {"input": "printf '%s\\n' /root/.agents/skills/iwe-v18/SKILL.md"},
        "observation": {"stdout": "path only"},
    }
    assert not confounded(harmless)


def test_generated_verifier_excludes_generated_workspace_noise(tmp_path: Path) -> None:
    parsed = ast.parse(VERIFIER)
    tree_function = next(
        node for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name == "tree"
    )
    namespace: dict[str, object] = {"hashlib": __import__("hashlib")}
    exec(
        compile(ast.Module(body=[tree_function], type_ignores=[]), "<verifier-tree>", "exec"),
        namespace,
    )
    (tmp_path / "source.py").write_text("pass\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__/source.cpython-313.pyc").write_bytes(b"generated")
    (tmp_path / ".DS_Store").write_bytes(b"generated")

    tree = cast(Callable[[Path], list[dict[str, object]]], namespace["tree"])
    manifest = tree(tmp_path)

    assert [item["path"] for item in manifest] == ["source.py"]


def test_pair_generation_is_byte_symmetric_except_arm_metadata(tmp_path: Path) -> None:
    runtime, fixtures = fixture_inputs(tmp_path)
    suite = load_suite(ROOT / "evals/suites/skill-guidance-ab.yaml").model_copy(update={"scenarios": ("summarize-one-topic",)})
    config = load_config(ROOT / "evals/config.yaml")
    guided = generate_dataset(root=tmp_path / "datasets", suite=suite, config=config, catalog_path=ROOT / "evals/scenarios/iwe.yaml", fixture_roots=fixtures, runtime=runtime, arm="skill")
    control = generate_dataset(root=tmp_path / "datasets", suite=suite, config=config, catalog_path=ROOT / "evals/scenarios/iwe.yaml", fixture_roots=fixtures, runtime=runtime, arm="no-skill")
    for relative in ("instruction.md", "environment/Dockerfile", "tests/Dockerfile", "tests/test.sh", "tests/verify.py"):
        assert (guided / "summarize-one-topic--sample-001" / relative).read_bytes() == (control / "summarize-one-topic--sample-001" / relative).read_bytes()


def test_unavailable_runtime_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "iwe"
    target = tmp_path / "bin" / "iwe"
    source.write_bytes(b"real")
    _materialize_runtime(source, target, "unavailable")
    assert target.read_text() == "#!/bin/sh\nprintf '%s\\n' 'iwe: unavailable in this scenario' >&2\nexit 127\n"
    assert target.stat().st_mode & 0o111
    with pytest.raises(ValueError, match="unknown runtime mode"):
        _materialize_runtime(source, target, "future")


def test_embedded_postcondition_catalog_is_self_contained(tmp_path: Path) -> None:
    catalog = scenario_map(ROOT / "evals/scenarios/iwe.yaml")
    sealed = tmp_path / "scenario-catalog.yaml"
    sealed.write_text(json.dumps({"schema_version": 2, "scenarios": list(catalog.values())}))
    assert scenario_map(sealed) == catalog