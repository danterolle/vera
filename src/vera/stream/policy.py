from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionPolicy:
    port_scan_threshold: int = 10
    port_scan_window_seconds: int = 60
    auth_failure_threshold: int = 5
    auth_failure_window_seconds: int = 300
    syn_burst_threshold: int = 20
    syn_burst_window_seconds: int = 10
