"""Stable API alias for port-based DB discovery (Zero-Touch plan)."""

from __future__ import annotations

from openclaw_launcher.services.db_discovery_scanner import (
    PORT_ENGINE,
    DetectedService,
    open_services_only,
    probe_port,
    scan_database_ports,
)

__all__ = [
    "PORT_ENGINE",
    "DetectedService",
    "DatabaseScanner",
    "open_services_only",
    "probe_port",
    "scan_database_ports",
]


class DatabaseScanner:
    """Facade: scan(host) -> list[DetectedService]."""

    @staticmethod
    def scan(host: str = "127.0.0.1") -> list[DetectedService]:
        return scan_database_ports(host)

    @staticmethod
    def open_only(host: str = "127.0.0.1") -> list[DetectedService]:
        return open_services_only(host)
