"""Validated, nested view model shared by absolute and paired reports."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .bundle import ValidatedBundle
from .summary import SummaryV6


def validate_publication_filename(output: Path) -> None:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md", output.name) is None:
        raise ValueError("publication filename must be a portable Markdown filename")


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ReportIdentity(ReportModel):
    run_id: str
    report_revision: str
    suite_id: str
    suite_kind: Literal["absolute", "paired"]
    run_purpose: str
    arms: tuple[dict, ...]


class ReportExecution(ReportModel):
    agent_name: str
    agent_version: str
    worker_model: str
    worker_reasoning: str
    judge_backend: str
    judge_model: str
    judge_reasoning: str
    runtime_version: str
    runtime_sha256: str
    harbor_version: str
    node_version: str
    agent_image_sha256: str
    verifier_image_sha256: str


class ReportProvenance(ReportModel):
    skill_name: str
    skill_version: str
    skill_url: str
    skill_sha256: str
    source_commit: str
    source_tree_sha256: str
    harness_repository: str
    harness_commit: str
    harness_tree_sha256: str
    config_sha256: str
    suite_sha256: str
    catalog_sha256: str
    effective_suite_sha256: str
    fixture_registry_sha256: str
    task_checksums: dict[str, str]


class ReportPublication(ReportModel):
    checksum_name: str
    evidence_link: str | None


class ReportTelemetry(ReportModel):
    schema_version: int
    scope: str
    network_scope: str
    disk_scope: str
    rootfs_scope: str
    logical_cpus: int
    total_memory_bytes: int
    total_swap_bytes: int
    sample_count: int
    cpu_percent_max: float
    load1_max: float
    mem_available_bytes_min: int
    swap_free_bytes_min: int
    running_containers_max: int
    docker_oom_events: int
    terminal_status: str
    sampling_errors: int
    network_rx_bytes_per_second_max: float
    network_tx_bytes_per_second_max: float
    disk_read_bytes_per_second_max: float
    disk_write_bytes_per_second_max: float
    rootfs_used_bytes_max: int
    rootfs_free_bytes_min: int
    network_rx_bytes_total: int
    network_tx_bytes_total: int
    disk_read_bytes_total: int
    disk_write_bytes_total: int


class ReportContext(ReportModel):
    summary: SummaryV6
    identity: ReportIdentity
    execution: ReportExecution
    provenance: ReportProvenance
    publication: ReportPublication
    telemetry: ReportTelemetry

    @classmethod
    def from_bundle(
        cls, bundle: ValidatedBundle, *, output: Path, repository: str,
        include_evidence: bool, telemetry: dict[str, int | float | str],
    ) -> "ReportContext":
        validate_publication_filename(output)
        summary, manifest, suite, provenance = bundle.summary, bundle.manifest, bundle.suite, bundle.provenance
        if summary.analysis.kind != suite.kind:
            raise ValueError("summary analysis kind does not match the validated effective suite")
        agent, judge = bundle.config.agents[manifest.agent], bundle.config.judge
        match = re.search(r"-v(\d+)$", output.stem)
        return cls(
            summary=summary,
            identity=ReportIdentity(
                run_id=manifest.run_id, report_revision=f"v{match.group(1)}" if match else "unversioned",
                suite_id=suite.id, suite_kind=suite.kind, run_purpose=manifest.run_purpose,
                arms=tuple(arm.model_dump(mode="json") for arm in suite.arms),
            ),
            execution=ReportExecution(
                agent_name=manifest.agent, agent_version=manifest.agent_version,
                worker_model=agent.model, worker_reasoning=agent.reasoning,
                judge_backend=manifest.judge_auth_mode, judge_model=judge.model, judge_reasoning=judge.reasoning,
                runtime_version=provenance.runtime_version, runtime_sha256=provenance.runtime_sha256,
                harbor_version=provenance.harbor_version, node_version=provenance.node_version,
                agent_image_sha256=provenance.image_digests["agent"],
                verifier_image_sha256=provenance.image_digests["verifier"],
            ),
            provenance=ReportProvenance(
                skill_name=bundle.skill.name, skill_version=bundle.skill.version, skill_url=provenance.source_url,
                skill_sha256=provenance.selected_skill_sha256, source_commit=provenance.source_commit,
                source_tree_sha256=provenance.source_tree_sha256, harness_repository=repository,
                harness_commit=provenance.harness_commit, harness_tree_sha256=provenance.harness_tree_sha256,
                config_sha256=provenance.config_sha256, suite_sha256=provenance.suite_sha256,
                catalog_sha256=provenance.scenario_catalog_sha256,
                effective_suite_sha256=provenance.effective_suite_sha256,
                fixture_registry_sha256=provenance.fixture_registry_sha256,
                task_checksums=provenance.task_checksums,
            ),
            publication=ReportPublication(
                checksum_name=output.name + ".sha256",
                evidence_link=f"{output.with_suffix('.evidence').name}/run-seal.json" if include_evidence else None,
            ),
            telemetry=ReportTelemetry.model_validate(telemetry),
        )
