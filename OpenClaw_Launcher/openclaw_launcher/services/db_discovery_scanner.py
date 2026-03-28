from __future__ import annotations

import socket
from dataclasses import dataclass

PORT_ENGINE: dict[int, tuple[str, str]] = {
    3306: ("mysql", "MySQL / MariaDB"),
    5432: ("postgresql", "PostgreSQL"),
    1433: ("mssql", "Microsoft SQL Server"),
    27017: ("mongodb", "MongoDB"),
}


@dataclass
class DetectedService:
    port: int
    engine: str
    label: str
    host: str
    open: bool


def probe_port(host: str, port: int, timeout_sec: float = 0.35) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_sec)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def scan_database_ports(host: str = "127.0.0.1") -> list[DetectedService]:
    out: list[DetectedService] = []
    for port, (engine, label) in sorted(PORT_ENGINE.items()):
        is_open = probe_port(host, port)
        out.append(
            DetectedService(port=port, engine=engine, label=label, host=host, open=is_open)
        )
    return out


def open_services_only(host: str = "127.0.0.1") -> list[DetectedService]:
    return [d for d in scan_database_ports(host) if d.open]
