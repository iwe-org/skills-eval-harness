"""Command line entrypoint for the Harbor-only evaluation harness."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

from harbor.models.job.result import TrialResult

from .acceptance import CURRENT_ACCEPTANCE_POLICY
from .bundle import validate_run_bundle
from .dataset import generate_dataset, scenario_map
from .fixtures import (
    fixture_source_name,
    load_fixture_sources,
    materialize_fixture,
    validate_fixture_roots,
)
from .hashing import (
    atomic_write_json,
    harbor_content_sha256,
    harbor_skill_sha256,
    sha256_bytes,
    sha256_file,
    sha256_tree,
)
from .judge import JUDGE_SCALE, build_evidence, build_judge_messages, derive_cell_outcome
from .judge_client import EquivalentJudgeCache, _retry_judge, judge_cell
from .models import AnalysisPlan, Agent, HarnessConfig, Suite, load_config, load_suite, scenario_family, validate_run_id
from .provenance import FixtureRevision, Provenance, seal_run, verify_harbor_lock, verify_materialized
from .publish import publish
from .security import (
    assert_no_secret_content,
    assert_no_secret_files,
    assert_symmetric_datasets,
    collect_secret_needles,
    redact_secret_content,
    selected_environment,
    staged_codex_auth,
    validate_codex_auth,
)
from .source import materialize_git_identity, resolve_skill, verify_runtime, write_git_commit_object
from .results import (
    normalized_judge_input,
    trial_evidence,
    trial_scenario_outcome,
    validate_job,
    write_summary,
)
from .telemetry import TelemetryRecorder, set_terminal_status

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "evals/config.yaml"
SCENARIOS = ROOT / "evals/scenarios/iwe.yaml"
FIXTURE_SOURCES = ROOT / "evals/fixtures/sources.json"


def _fixture(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("fixture must be NAME=PATH")
    name, raw = value.split("=", 1)
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"fixture path is not a directory: {path}")
    return name, path


def _clean_git() -> tuple[str, bool]:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip())
    return commit, dirty


def _agents_template(source: str | None) -> tuple[bytes | None, str | None]:
    if source is None:
        return None, None
    if source.startswith(("https://", "http://")):
        with urllib.request.urlopen(source, timeout=30) as response:
            payload = response.read(1_048_577)
    else:
        path = Path(source).expanduser().resolve()
        payload = path.read_bytes()
        source = str(path)
    if len(payload) > 1_048_576:
        raise ValueError("AGENTS template exceeds 1 MiB")
    return payload, source


def validate_repository() -> None:
    config = load_config(CONFIG)
    if any(profile.reasoning is None for profile in config.agents.values()):
        raise ValueError("every live worker profile must declare reasoning")
    installed = importlib.metadata.version("harbor")
    if installed != config.harbor_version:
        raise ValueError(f"Harbor version mismatch: config={config.harbor_version}, installed={installed}")
    catalog = scenario_map(SCENARIOS)
    for path in sorted((ROOT / "evals/suites").glob("*.yaml")):
        suite = load_suite(path)
        missing = sorted(set(suite.scenarios) - set(catalog))
        if missing:
            raise ValueError(f"{path.name} references unknown scenarios: {missing}")
    image = config.container.image
    if "@sha256:" not in image or len(image.rsplit("@sha256:", 1)[1]) != 64:
        raise ValueError("container image must be digest pinned")


def verify_agent_image(config: HarnessConfig) -> None:
    image = config.container.agent_image
    inspected = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
    )
    if inspected.returncode != 0 or inspected.stdout.strip() != config.container.agent_image_id:
        raise ValueError(
            f"required immutable agent image is unavailable or has the wrong ID: {image}"
        )
    expected = {
        "node": f"v{config.container.node_version}",
        "codex": f"codex-cli {config.agents['codex'].version}",
    }
    command = (
        f'test "$(node --version)" = "{expected["node"]}" && '
        f'test "$(codex --version)" = "{expected["codex"]}" && '
        f'claude --version | grep -F "{config.agents["claude"].version}"'
    )
    verified = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", image, "sh", "-lc", command],
        capture_output=True,
        text=True,
    )
    if verified.returncode != 0:
        raise ValueError("immutable agent image does not contain the configured toolchain versions")


def _agent_kwargs(profile: Agent) -> list[str]:
    """Render immutable Harbor agent settings for every worker trial."""
    if profile.reasoning is None:
        raise ValueError("worker reasoning must be explicit before execution")
    return [
        "--ak", f"version={profile.version}",
        "--ak", f"reasoning_effort={profile.reasoning}",
    ]


def prepare(args: argparse.Namespace) -> Path:
    validate_repository()
    config = load_config(CONFIG)
    verify_agent_image(config)
    profile = config.agents[args.agent]
    global_concurrency = _resolve_global_concurrency(args.jobs, config)
    judge_concurrency = _resolve_judge_concurrency(args.judge_jobs, config)
    suite_path = Path(args.suite).resolve()
    suite = load_suite(suite_path)
    samples = suite.default_samples if args.samples is None else args.samples
    if samples < 1:
        raise ValueError("samples must be a positive integer")
    args.samples = samples
    if getattr(args, "run_purpose", "diagnostic") == "production" and (
        args.scenario or samples != suite.default_samples
    ):
        raise ValueError("production runs require the complete preregistered scenario matrix and sample count")
    if args.scenario:
        unknown = sorted(set(args.scenario) - set(suite.scenarios))
        if unknown:
            raise ValueError(f"unknown selected scenarios: {unknown}")
        suite = suite.model_copy(update={"scenarios": list(args.scenario)})
    runtime, runtime_sha = verify_runtime(Path(args.runtime), args.runtime_version)
    if config.runtimes.get(args.runtime_version) != runtime_sha:
        raise ValueError("runtime bytes do not match the canonical version registry")
    agents_template, _ = _agents_template(args.agents_template)
    fixtures = dict(args.fixture)
    commit, dirty = _clean_git()
    try:
        suite_repository_path = suite_path.relative_to(ROOT).as_posix()
    except ValueError:
        suite_repository_path = None
    if getattr(args, "run_purpose", "diagnostic") == "production":
        tracked_suite = (
            suite_repository_path is not None
            and Path(suite_repository_path).parent.as_posix() == "evals/suites"
            and subprocess.run(
                ["git", "ls-files", "--error-unmatch", suite_repository_path],
                cwd=ROOT,
                capture_output=True,
            ).returncode == 0
        )
        if dirty or not tracked_suite:
            raise ValueError("production runs require a clean harness and a tracked canonical suite")
    source = resolve_skill(args.skill_source, Path(args.cache).resolve() / "skills")
    if source.source_url.split("/tree/", 1)[0].rstrip("/").removesuffix(".git") not in {
        value.rstrip("/").removesuffix(".git") for value in config.skill_repositories
    }:
        raise ValueError("skill source repository is not in the canonical registry")
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to reuse evaluation output directory: {output}")
    inputs = output / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    catalog = scenario_map(SCENARIOS)
    shutil.copy2(CONFIG, inputs / "config.yaml")
    atomic_write_json(inputs / "scenario-catalog.yaml", {"schema_version": 2, "scenarios": list(catalog.values())})
    shutil.copy2(suite_path, inputs / "suite.yaml")
    shutil.copy2(FIXTURE_SOURCES, inputs / "fixture-sources.json")
    atomic_write_json(inputs / "effective-suite.json", suite.model_dump(mode="json"))
    registry = load_fixture_sources(FIXTURE_SOURCES)
    required_fixtures = {catalog[scenario_id]["fixture"] for scenario_id in suite.scenarios}
    fixture_sources = validate_fixture_roots(fixtures, required_fixtures, FIXTURE_SOURCES)
    resolved_fixtures: dict[str, Path] = {}
    for name in sorted(required_fixtures):
        source_name = fixture_source_name(name, registry)
        destination = inputs / "materialized-fixtures" / name
        materialize_fixture(Path(fixtures[source_name]).resolve(), destination, name)
        resolved_fixtures[name] = destination
    shutil.copy2(runtime, inputs / "runtime")
    materialize_git_identity(
        source.repository_root,
        inputs / "source-repository",
        inputs / "source-commit-object",
    )
    skill_relative = source.skill_root.relative_to(source.repository_root)
    shutil.copytree(inputs / "source-repository" / skill_relative, inputs / "selected-skill")
    materialize_git_identity(ROOT, inputs / "harness-repository", inputs / "harness-commit-object")
    for name in fixture_sources:
        shutil.copytree(fixtures[name], inputs / "fixtures" / name, ignore=shutil.ignore_patterns(".git"))
        write_git_commit_object(
            Path(fixtures[name]).resolve(),
            inputs / "fixture-commit-objects" / name,
        )
    if agents_template is not None:
        (inputs / "AGENTS.md").write_bytes(agents_template)
    datasets: dict[str, Path] = {}
    for arm in suite.arms:
        dataset = generate_dataset(
            root=output / "datasets", suite=suite, config=config, catalog_path=SCENARIOS,
            fixture_roots=resolved_fixtures, runtime=inputs / "runtime", arm=arm.id, agent=args.agent, samples=args.samples,
            agents_template=agents_template,
        )
        datasets[arm.id] = dataset
        for task in dataset.iterdir():
            if task.is_dir():
                assert_no_secret_files(task)
    if len(datasets) == 2:
        assert_symmetric_datasets(*datasets.values())
    tasks = {
        f"{arm}/{task.name}": harbor_content_sha256(task)
        for arm, dataset in datasets.items()
        for task in sorted(dataset.iterdir()) if task.is_dir()
    }
    verifier_image_digest = config.container.image.rsplit("@sha256:", 1)[1]
    agent_image_digest = config.container.agent_image_id.removeprefix("sha256:")
    provenance = Provenance(
        source_url=source.source_url,
        source_commit=source.commit,
        source_tree_sha256=source.repository_sha256,
        selected_skill=source.skill_root.name,
        selected_skill_sha256=source.skill_sha256,
        selected_skill_harbor_sha256=harbor_skill_sha256(source.skill_root),
        runtime_version=args.runtime_version,
        runtime_sha256=runtime_sha,
        harness_commit=commit,
        harness_tree_sha256=sha256_tree(inputs / "harness-repository"),
        harness_dirty=dirty,
        suite_sha256=sha256_file(inputs / "suite.yaml"),
        effective_suite_sha256=sha256_file(inputs / "effective-suite.json"),
        scenario_catalog_sha256=sha256_file(inputs / "scenario-catalog.yaml"),
        config_sha256=sha256_file(inputs / "config.yaml"),
        fixture_registry_sha256=sha256_file(inputs / "fixture-sources.json"),
        harbor_version=config.harbor_version,
        node_version=config.container.node_version,
        agent_versions={name: value.version for name, value in config.agents.items()},
        task_checksums=tasks,
        image_digests={"agent": agent_image_digest, "verifier": verifier_image_digest},
        fixture_sources={
            name: FixtureRevision.model_validate(
                {**value, "payload_sha256": sha256_tree(inputs / "fixtures" / name)}
            )
            for name, value in fixture_sources.items()
        },
        agents_template_sha256=sha256_bytes(agents_template) if agents_template is not None else None,
        worker_auth_mode=args.codex_auth,
        judge_auth_mode=args.judge_auth,
        judge_concurrency=judge_concurrency,
    )
    manifest = {
        "schema_version": 1,
        "run_id": validate_run_id(output.name),
        "suite": suite.model_dump(mode="json"),
        "suite_repository_path": suite_repository_path,
        "agent": args.agent,
        "agent_version": profile.version,
        "node_version": config.container.node_version,
        "worker_auth_mode": args.codex_auth,
        "judge_auth_mode": args.judge_auth,
        "evidence_protocol": "judge-evidence-v3",
        "samples": args.samples,
        "suite_default_samples": load_suite(suite_path).default_samples,
        "run_purpose": getattr(args, "run_purpose", "diagnostic"),
        "execution": {
            "global_concurrency": global_concurrency,
            "judge_concurrency": judge_concurrency,
            "arm_concurrency_batches": _arm_concurrency_batches(
                tuple(arm.id for arm in suite.arms), global_concurrency
            ),
        },
        "datasets": {key: str(value.relative_to(output)) for key, value in datasets.items()},
    }
    atomic_write_json(output / "run-manifest.json", manifest)
    atomic_write_json(output / "provenance.json", provenance.model_dump(mode="json"))
    return output


def _validate_docker() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Harbor v0.21.0 requires a Docker-compatible CLI and daemon; Podman is not a supported drop-in for compose/buildx/cp")
    subprocess.run([docker, "compose", "version"], check=True, capture_output=True, text=True)


def _codex_auth_args(staged_auth: Path | None) -> list[str]:
    if staged_auth is None:
        return []
    return ["--ae", f"CODEX_AUTH_JSON_PATH={staged_auth}"]


def _required_credentials(config, agent: str, worker_auth: str, judge_auth: str) -> set[str]:
    required: set[str] = set()
    if worker_auth == "api-key":
        required.add(config.agents[agent].credential_env)
    if judge_auth == "api-key":
        required.add(config.judge.credential_env)
    return required


def _resolve_global_concurrency(value: int | None, config) -> int:
    total = config.execution.global_concurrency if value is None else value
    if not 1 <= total <= 32:
        raise ValueError("global concurrency must be between 1 and 32")
    return total


def _resolve_judge_concurrency(value: int | None, config) -> int:
    total = config.judge.concurrency if value is None else value
    if not 1 <= total <= 32:
        raise ValueError("judge concurrency must be between 1 and 32")
    return total


def _run_concurrently_in_order(items: list, jobs: int, function):
    """Bound concurrent work while preserving canonical input order."""
    if not 1 <= jobs <= 32:
        raise ValueError("judge concurrency must be between 1 and 32")
    with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="skills-eval-judge") as executor:
        return list(executor.map(function, items))


def _arm_concurrency_batches(arm_ids: tuple[str, ...], total: int) -> tuple[dict[str, int], ...]:
    if not arm_ids:
        raise ValueError("at least one arm is required")
    if total < len(arm_ids):
        return tuple({arm_id: 1} for arm_id in arm_ids)
    per_arm = total // len(arm_ids)
    return ({arm_id: per_arm for arm_id in arm_ids},)


def _scenario_family(scenario: dict) -> str:
    return scenario_family(scenario)


def _required_cell_pass(role: str | None, semantic_pass: bool, safety_score: float) -> bool:
    scores = {"task_correctness": 5.0 if semantic_pass else 0.0, "safety": safety_score}
    return CURRENT_ACCEPTANCE_POLICY.evaluate_cell(scores, role)[1]


def run(args: argparse.Namespace) -> Path:
    run_started = time.monotonic()
    config = load_config(CONFIG)
    if args.codex_auth == "chatgpt" and args.agent != "codex":
        raise ValueError("ChatGPT worker auth is only supported for codex")
    subscription_required = args.codex_auth == "chatgpt" or args.judge_auth == "chatgpt"
    auth_source = validate_codex_auth(
        "codex",
        "chatgpt" if subscription_required else "api-key",
        args.codex_auth_json,
    )
    env = selected_environment(
        config,
        args.agent,
        include_provider_credential=args.codex_auth == "api-key",
    )
    _validate_docker()
    profile = config.agents[args.agent]
    required_credentials = _required_credentials(config, args.agent, args.codex_auth, args.judge_auth)
    missing_credentials = [name for name in required_credentials if not env.get(name) and not os.environ.get(name)]
    if missing_credentials:
        raise RuntimeError(f"missing required credential environment names: {sorted(missing_credentials)}")
    secret_needles = collect_secret_needles(
        {name: env.get(name) or os.environ.get(name, "") for name in required_credentials},
        set(required_credentials),
        auth_source,
    )
    telemetry_fd, telemetry_name = tempfile.mkstemp(prefix="skills-eval-telemetry-", suffix=".json")
    os.close(telemetry_fd)
    telemetry_temp = Path(telemetry_name)
    telemetry_temp.unlink()
    telemetry = TelemetryRecorder(telemetry_temp)
    telemetry.start()
    try:
        run_root = prepare(args)
    except Exception:
        try:
            telemetry.stop("failed")
        finally:
            telemetry_temp.unlink(missing_ok=True)
        raise
    telemetry.output = run_root / "device-telemetry.json"
    try:
        _execute_run(
            args=args,
            run_root=run_root,
            config=config,
            env=env,
            profile=profile,
            auth_source=auth_source,
            secret_needles=secret_needles,
            run_started=run_started,
        )
    finally:
        try:
            telemetry.stop("failed" if sys.exc_info()[0] is not None else "completed")
        finally:
            for root in (run_root / "jobs", run_root / "cells", run_root / "summary.json"):
                if root.exists():
                    redact_secret_content(root, secret_needles)
            try:
                assert_no_secret_content(
                    (run_root / "jobs", run_root / "cells", run_root / "summary.json"),
                    secret_needles,
                )
            except Exception:
                set_terminal_status(run_root / "device-telemetry.json", "failed")
                raise
    try:
        bundle = validate_run_bundle(run_root, require_seal=False)
        if bundle.summary.valid is not True:
            set_terminal_status(run_root / "device-telemetry.json", "failed")
            validate_run_bundle(run_root, require_seal=False)
            seal_run(run_root)
            raise RuntimeError(f"evaluation completed with invalid terminal evidence: {run_root}")
        seal_run(run_root)
    except Exception:
        if not (run_root / "run-seal.json").exists():
            set_terminal_status(run_root / "device-telemetry.json", "failed")
        raise
    return run_root


def _execute_run(
    *, args, run_root: Path, config, env: dict[str, str], profile,
    auth_source: Path | None, secret_needles: tuple[bytes, ...], run_started: float,
) -> None:
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    provenance = Provenance.model_validate_json((run_root / "provenance.json").read_text(encoding="utf-8")).validated()
    config = load_config(run_root / "inputs/config.yaml")
    source = resolve_skill(args.skill_source, Path(args.cache).resolve() / "skills")
    runtime, _ = verify_runtime(Path(args.runtime), args.runtime_version)
    verify_materialized(
        provenance,
        source_tree_sha256=source.repository_sha256,
        skill_tree_sha256=source.skill_sha256,
        runtime=runtime,
        suite=run_root / "inputs/suite.yaml",
        scenarios=run_root / "inputs/scenario-catalog.yaml",
        config=run_root / "inputs/config.yaml",
    )
    effective_suite = json.loads((run_root / "inputs/effective-suite.json").read_text(encoding="utf-8"))
    if manifest["suite"] != effective_suite or sha256_file(run_root / "inputs/effective-suite.json") != provenance.effective_suite_sha256:
        raise ValueError("effective suite provenance mismatch")
    for arm, dataset_value in manifest["datasets"].items():
        dataset = (run_root / dataset_value).resolve()
        if not dataset.is_relative_to(run_root):
            raise ValueError("dataset path escapes the run directory")
        for task in sorted(path for path in dataset.iterdir() if path.is_dir()):
            key = f"{arm}/{task.name}"
            if harbor_content_sha256(task) != provenance.task_checksums.get(key):
                raise ValueError(f"materialized task provenance mismatch: {key}")
    jobs = run_root / "jobs"
    job_dirs: dict[str, Path] = {}
    job_errors: dict[str, str] = {}
    global_concurrency = manifest["execution"]["global_concurrency"]
    judge_concurrency = manifest["execution"]["judge_concurrency"]
    if provenance.judge_concurrency != judge_concurrency:
        raise ValueError("judge concurrency provenance mismatch")
    arms = {arm["id"]: arm for arm in manifest["suite"]["arms"]}

    def run_arm(arm_id: str, arm_concurrency: int, staged_auth: Path | None) -> Path:
        arm = arms[arm_id]
        command = [
            str(ROOT / ".venv/bin/harbor"), "run", "-p", str(run_root / manifest["datasets"][arm_id]),
            "-a", profile.harbor_name, "-m", profile.model, "-k", "1",
            "-n", str(arm_concurrency), "--max-retries", str(config.execution.retries), "--env", "docker",
            "--jobs-dir", str(jobs), "--job-name", f"{run_root.name}-{arm_id}", "--yes",
        ]
        command.extend(_agent_kwargs(profile))
        command.extend(_codex_auth_args(staged_auth))
        if arm["skill"]:
            command.extend(["--skill", str(source.skill_root)])
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        return jobs / f"{run_root.name}-{arm_id}"

    auth_context = staged_codex_auth(auth_source) if args.codex_auth == "chatgpt" and auth_source is not None else nullcontext(None)
    with auth_context as staged_auth:
        arm_ids = tuple(arms)
        for allocation in _arm_concurrency_batches(arm_ids, global_concurrency):
            with ThreadPoolExecutor(max_workers=len(allocation)) as executor:
                futures = {
                    arm_id: executor.submit(run_arm, arm_id, arm_concurrency, staged_auth)
                    for arm_id, arm_concurrency in allocation.items()
                }
                for arm_id in allocation:
                    try:
                        job_dirs[arm_id] = futures[arm_id].result()
                    except subprocess.CalledProcessError:
                        job_dirs[arm_id] = jobs / f"{run_root.name}-{arm_id}"
                        job_errors[arm_id] = "harbor_process_failed"
    for arm_id, job_dir in job_dirs.items():
        if job_dir.is_dir() and redact_secret_content(job_dir, secret_needles):
            job_errors[arm_id] = "secret_exposure_redacted"
    judge_context = (
        staged_codex_auth(auth_source)
        if args.judge_auth == "chatgpt" and auth_source is not None
        else nullcontext(None)
    )
    with judge_context as staged_judge_auth:
        catalog = scenario_map(run_root / "inputs/scenario-catalog.yaml")
        cells: list[dict] = []
        trials: list[tuple[dict, TrialResult, Path]] = []

        def record_invalid(arm: dict, scenario_id: str, sample: int, reason: str) -> None:
            cell = {
                "arm": arm["id"],
                "scenario_id": scenario_id,
                "family": _scenario_family(catalog[scenario_id]),
                "sample": sample,
                "valid": False,
                "pass": False,
                "required_pass": False,
                "invalid_reason": reason,
                "scores": {},
                "wall_time_seconds": None,
            }

            cells.append(cell)
            atomic_write_json(run_root / "cells" / f"{arm['id']}--{scenario_id}--{sample}.json", cell)

        for arm in manifest["suite"]["arms"]:
            arm_id = arm["id"]
            if arm_id in job_errors:
                for scenario_id in manifest["suite"]["scenarios"]:
                    for sample in range(1, manifest["samples"] + 1):
                        record_invalid(arm, scenario_id, sample, job_errors[arm_id])
                continue
            try:
                job = validate_job(
                    job_dirs[arm_id],
                    expected_trials=len(manifest["suite"]["scenarios"]) * manifest["samples"],
                    require_mechanical_success=False,
                    allow_failed_trials=True,
                )
                lock = json.loads((job_dirs[arm_id] / "lock.json").read_text(encoding="utf-8"))
                arm_concurrency = max(
                    batch.get(arm_id, 0) for batch in manifest["execution"]["arm_concurrency_batches"]
                )
                verify_harbor_lock(
                    provenance,
                    lock,
                    arm_id=arm_id,
                    n_concurrent=arm_concurrency,
                    retries=config.execution.retries,
                    agent_name=profile.harbor_name,
                    agent_version=profile.version,
                    reasoning_effort=profile.reasoning,
                    model=profile.model,
                    skill_enabled=arm["skill"],
                )
            except (OSError, ValueError, json.JSONDecodeError):
                for scenario_id in manifest["suite"]["scenarios"]:
                    for sample in range(1, manifest["samples"] + 1):
                        record_invalid(arm, scenario_id, sample, "harbor_or_verifier_validation_failed")
                continue
            trials.extend((arm, trial, job_dirs[arm_id]) for trial in job.trial_results)

        def trial_identity(item: tuple[dict, TrialResult, Path]) -> tuple[str, int, int]:
            arm, trial, _ = item
            task_id = trial.task_name.removeprefix("iwe/")
            scenario_id, sample_text = task_id.rsplit("--sample-", 1)
            sample = int(sample_text)
            first_role = "treatment" if sample % 2 else "control"
            return scenario_id, sample, 0 if arm["role"] == first_role else 1

        judge_cache = EquivalentJudgeCache()

        def judge_trial(item: tuple[dict, TrialResult, Path]) -> tuple[dict, str, int, dict | None, str | None]:
            arm, trial, job_dir = item
            arm_id = arm["id"]
            task_id = trial.task_name.removeprefix("iwe/")
            scenario_id, sample_text = task_id.rsplit("--sample-", 1)
            sample = int(sample_text)
            if trial.exception_info is not None:
                return arm, scenario_id, sample, None, "trial_exception"
            try:
                scenario_outcome, failures = trial_scenario_outcome(job_dir, trial)
            except (OSError, ValueError, json.JSONDecodeError):
                return arm, scenario_id, sample, None, "harbor_or_verifier_validation_failed"
            try:
                evidence = build_evidence(
                    trial_evidence(job_dir, trial.trial_name)
                )
                judge_messages = build_judge_messages(
                    scenario=catalog[scenario_id], evidence=evidence, scale=JUDGE_SCALE
                )
                equivalence_key = normalized_judge_input(judge_messages)

                def invoke_judge():
                    return _retry_judge(
                        lambda: judge_cell(
                            config=config,
                            scenario=catalog[scenario_id],
                            evidence=evidence,
                            auth_mode=args.judge_auth,
                            auth_json=staged_judge_auth,
                        ),
                        max_attempts=config.judge.max_attempts,
                    )

                verdict = (
                    judge_cache.get_or_invoke(equivalence_key, invoke_judge)
                    if equivalence_key is not None
                    else invoke_judge()
                )
            except Exception:
                return arm, scenario_id, sample, None, "judge_validation_failed"
            scores, passed, required = derive_cell_outcome(
                verdict,
                role=arm["role"],
                agent=args.agent,
                scenario_outcome=scenario_outcome,
            )

            wall_time = (trial.finished_at - trial.started_at).total_seconds() if trial.finished_at and trial.started_at else None
            n_input, n_cache, n_output, cost = trial.compute_token_cost_totals()
            cell = {
                "arm": arm_id,
                "scenario_id": scenario_id,
                "family": _scenario_family(catalog[scenario_id]),
                "sample": sample,
                "valid": True,
                "pass": passed,
                "required_pass": required,
                "scenario_outcome": scenario_outcome,
                "scenario_failures": failures,
                "scores": scores,
                "wall_time_seconds": wall_time,
                "n_input_tokens": n_input,
                "n_cache_tokens": n_cache,
                "n_output_tokens": n_output,
                "cost_usd": cost,
                "evidence": [evidence_item.model_dump(mode="json") for evidence_item in evidence],
                "judge_messages": judge_messages,
                "verdict": verdict.model_dump(mode="json"),
            }
            return arm, scenario_id, sample, cell, None

        ordered_trials = sorted(trials, key=trial_identity)
        for arm, scenario_id, sample, cell, invalid_reason in _run_concurrently_in_order(
            ordered_trials, judge_concurrency, judge_trial
        ):
            if invalid_reason is not None:
                record_invalid(arm, scenario_id, sample, invalid_reason)
                continue
            assert cell is not None
            cells.append(cell)
            atomic_write_json(run_root / "cells" / f"{arm['id']}--{scenario_id}--{sample}.json", cell)
        effective_suite = Suite.model_validate(manifest["suite"])
        expected_identities = {
            (arm["id"], scenario_id, sample)
            for arm in manifest["suite"]["arms"]
            for scenario_id in manifest["suite"]["scenarios"]
            for sample in range(1, manifest["samples"] + 1)
        }
        summary = write_summary(
            run_root / "summary.json",
            cells,
            expected_identities,
            expected_families={scenario_id: _scenario_family(catalog[scenario_id]) for scenario_id in manifest["suite"]["scenarios"]},
            analysis=AnalysisPlan.from_suite(
                effective_suite,
                families={scenario_id: _scenario_family(catalog[scenario_id]) for scenario_id in effective_suite.scenarios},
                samples=manifest["samples"],
            ),
            pipeline_elapsed_seconds=time.monotonic() - run_started,
            run_purpose=manifest["run_purpose"],
            samples_per_identity=manifest["samples"],
            preregistered_samples=manifest["suite"]["default_samples"],
        )
        for canonical_cell in summary.cells:
            payload = canonical_cell.model_dump(mode="json", by_alias=True)
            atomic_write_json(run_root / "cells" / f"{payload['arm']}--{payload['scenario_id']}--{payload['sample']}.json", payload)
        return None


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="skills-eval")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    for name in ("prepare", "run"):
        command = sub.add_parser(name)
        command.add_argument("--suite", required=True)
        command.add_argument("--skill-source", required=True)
        command.add_argument("--runtime", required=True)
        command.add_argument("--runtime-version", required=True)
        command.add_argument("--fixture", action="append", type=_fixture, required=True)
        command.add_argument("--agents-template", help="optional local path or URL applied identically to every arm")
        command.add_argument("--agent", choices=("codex", "claude"), default="codex")
        command.add_argument("--samples", type=int, help="samples per scenario (default: suite default_samples)")
        command.add_argument("--jobs", type=int, help="global Harbor trial concurrency across all arms (default: config value)")
        command.add_argument("--judge-jobs", type=int, help="concurrent judge calls (default: config value, normally 4)")
        command.add_argument("--scenario", action="append")
        command.add_argument("--cache", default=".cache/skills-eval")
        command.add_argument("--output", required=True)
        command.add_argument("--run-purpose", choices=("diagnostic", "production"), default="diagnostic")
        if name == "run":
            command.add_argument("--codex-auth", choices=("api-key", "chatgpt"), default="api-key")
            command.add_argument("--codex-auth-json", help="private Codex CLI auth.json used by subscription worker or judge")
            command.add_argument("--judge-auth", choices=("api-key", "chatgpt"), default="api-key")
    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("run")
    publish_parser.add_argument("output")
    publish_parser.add_argument(
        "--include-evidence",
        action="store_true",
        help="copy and stage the sealed evidence bundle (default: report and checksum only)",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "validate":
        validate_repository()
    elif args.command == "prepare":
        prepare(args)
    elif args.command == "run":
        run(args)
    elif args.command == "publish":
        publish(
            root=ROOT,
            run_dir=Path(args.run),
            output=Path(args.output),
            include_evidence=args.include_evidence,
        )
    return 0
