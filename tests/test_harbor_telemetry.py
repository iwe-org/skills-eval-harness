from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from skills_eval_harness.telemetry import TelemetryRecorder
from skills_eval_harness.telemetry import _rates, set_terminal_status, validate_device_telemetry


class StubbornProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: int) -> int:
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise subprocess.TimeoutExpired("docker events", timeout)
        return 0


def test_startup_failure_kills_stubborn_oom_monitor(tmp_path: Path) -> None:
    process = StubbornProcess()
    recorder = TelemetryRecorder(tmp_path / "telemetry.json", 0.01)
    with (
        patch("skills_eval_harness.telemetry.subprocess.Popen", return_value=process),
        patch.object(recorder, "_sample", side_effect=RuntimeError("sample failed")),
        pytest.raises(RuntimeError, match="sample failed"),
    ):
        recorder.start()
    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2
    assert recorder.oom_process is None


def test_sampling_failure_persists_failed_terminal_telemetry(tmp_path: Path) -> None:
    process = StubbornProcess()
    path = tmp_path / "telemetry.json"
    recorder = TelemetryRecorder(path, 100.0)
    with (
        patch("skills_eval_harness.telemetry.subprocess.Popen", return_value=process),
        patch("skills_eval_harness.telemetry._container_count", return_value=(0, True)),
    ):
        recorder.start()
        recorder.sampling_errors = 1
        with pytest.raises(RuntimeError, match="partial metrics were persisted"):
            recorder.stop()
    telemetry = validate_device_telemetry(path)
    assert getattr(telemetry, "terminal_status", None) == "failed"
    assert getattr(telemetry, "sampling_errors", None) == 1


def test_io_rates_are_derived_from_monotonic_host_counters() -> None:
    previous = {
        "elapsed_ms": 1000,
        "network_rx_bytes": 100,
        "network_tx_bytes": 200,
        "disk_read_bytes": 300,
        "disk_write_bytes": 400,
    }
    current = {
        "elapsed_ms": 3000,
        "network_rx_bytes": 2100,
        "network_tx_bytes": 4200,
        "disk_read_bytes": 6300,
        "disk_write_bytes": 8400,
    }
    assert _rates(previous, current) == {
        "network_rx_bytes_per_second": 1000.0,
        "network_tx_bytes_per_second": 2000.0,
        "disk_read_bytes_per_second": 3000.0,
        "disk_write_bytes_per_second": 4000.0,
    }


def test_device_telemetry_requires_network_disk_and_rootfs_measurements(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.json"
    path.write_text(__import__("json").dumps({
        "schema_version": 2,
        "started_unix_ms": 1000,
        "finished_unix_ms": 2000,
        "host": {
            "logical_cpus": 2,
            "total_memory_bytes": 4096,
            "total_swap_bytes": 0,
            "docker_metrics_available": True,
            "telemetry_scope": "whole-host",
            "network_scope": "default-route-interfaces",
            "disk_scope": "physical-block-devices",
            "filesystem_scope": "root-filesystem",
        },
        "samples": [{
            "elapsed_ms": 0,
            "cpu_percent": 25.0,
            "load1": 0.5,
            "mem_available_bytes": 2048,
            "swap_free_bytes": 0,
            "running_containers": 2,
            "network_rx_bytes": 100,
            "network_tx_bytes": 200,
            "disk_read_bytes": 300,
            "disk_write_bytes": 400,
            "rootfs_used_bytes": 500,
            "rootfs_free_bytes": 600,
            "network_rx_bytes_per_second": 0.0,
            "network_tx_bytes_per_second": 0.0,
            "disk_read_bytes_per_second": 0.0,
            "disk_write_bytes_per_second": 0.0,
        }],
        "peaks": {
            "cpu_percent": 25.0,
            "load1": 0.5,
            "running_containers": 2,
            "network_rx_bytes_per_second": 0.0,
            "network_tx_bytes_per_second": 0.0,
            "disk_read_bytes_per_second": 0.0,
            "disk_write_bytes_per_second": 0.0,
            "rootfs_used_bytes": 500,
        },
        "minima": {"mem_available_bytes": 2048, "swap_free_bytes": 0, "rootfs_free_bytes": 600},
        "totals": {"network_rx_bytes": 0, "network_tx_bytes": 0, "disk_read_bytes": 0, "disk_write_bytes": 0},
        "docker_oom_events": 0,
        "sampling_errors": 0,
        "terminal_status": "completed",
    }))
    assert validate_device_telemetry(path).schema_version == 2
    assert set_terminal_status(path, "failed").terminal_status == "failed"
    assert getattr(validate_device_telemetry(path), "terminal_status", None) == "failed"
