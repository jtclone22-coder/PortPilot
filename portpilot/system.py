"""What's listening where, WSL distros, Docker containers and the hosts file. Uses only built-in Windows
tools (netstat, tasklist, taskkill, wsl, docker if installed), so there is nothing to install.

Reading is always safe. Stopping something is an explicit call, refused for Windows' own processes.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

KNOWN_PORTS = {
    80: "web server", 443: "web server (HTTPS)", 1433: "SQL Server", 1883: "MQTT", 3000: "Node / React dev server",
    3001: "dev server", 3306: "MySQL", 4200: "Angular dev server", 4321: "Astro dev server", 5000: "Flask / ASP.NET",
    5173: "Vite dev server", 5174: "Vite dev server", 5432: "PostgreSQL", 5500: "Live Server", 5672: "RabbitMQ",
    6006: "Storybook", 6379: "Redis", 7860: "Gradio", 8000: "Python dev server (Django/uvicorn)", 8080: "web server / proxy",
    8081: "Metro / web server", 8188: "ComfyUI", 8501: "Streamlit", 8888: "Jupyter", 9000: "PHP-FPM / MinIO",
    9200: "Elasticsearch", 9229: "Node debugger", 11434: "Ollama", 15672: "RabbitMQ admin", 27017: "MongoDB",
    1234: "LM Studio", 8008: "dev server", 4000: "dev server", 5555: "Prisma Studio", 19000: "Expo",
}
# Never stopped by PortPilot, whatever the user clicks.
PROTECTED_NAMES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "spoolsv.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe",
    "msmpeng.exe", "securityhealthservice.exe", "memory compression", "lsaiso.exe", "wlanext.exe",
}


@dataclass
class Listener:
    protocol: str
    address: str
    port: int
    pid: int
    process: str = ""

    @property
    def label(self) -> str:
        return KNOWN_PORTS.get(self.port, "")

    @property
    def local_only(self) -> bool:
        return self.address in ("127.0.0.1", "::1")

    @property
    def browser_url(self) -> str:
        return f"http://localhost:{self.port}/"


def _run(command: list[str], runner=subprocess.run, timeout: float = 20) -> subprocess.CompletedProcess:
    return runner(command, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)


LISTEN_REMOTES = {"0.0.0.0:0", "[::]:0"}


def parse_netstat(text: str) -> list[Listener]:
    """`netstat -ano` output -> listening TCP sockets and bound UDP sockets."""
    found = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] not in ("TCP", "UDP"):
            continue
        local = parts[1]
        if parts[0] == "TCP":  # listening rows have no remote end; the word "LISTENING" is translated on other Windows
            if len(parts) < 5 or parts[2] not in LISTEN_REMOTES:
                continue
            pid = parts[4]
        else:
            pid = parts[-1]
        match = re.match(r"^\[?(.*?)\]?:(\d+)$", local)
        if not match or not pid.isdigit():
            continue
        address = match.group(1).split("%")[0]
        found.append(Listener(parts[0], address, int(match.group(2)), int(pid)))
    unique = {(l.protocol, l.address, l.port, l.pid): l for l in found}
    return sorted(unique.values(), key=lambda l: (l.port, l.protocol, l.address))


def parse_tasklist(text: str) -> dict[int, str]:
    names = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) >= 2 and row[1].isdigit():
            names[int(row[1])] = row[0]
    return names


def _decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(data) > 1 and data[1:2] == b"\x00"):
        return data.decode("utf-16-le", errors="replace").lstrip("\ufeff")
    return data.decode("utf-8", errors="replace")


def listeners(runner=subprocess.run, include_udp: bool = False) -> list[Listener]:
    found = parse_netstat(_decode(_run(["netstat", "-ano"], runner).stdout))
    names = parse_tasklist(_decode(_run(["tasklist", "/FO", "CSV", "/NH"], runner).stdout))
    for item in found:
        item.process = names.get(item.pid, "System" if item.pid == 4 else "")
    return [l for l in found if include_udp or l.protocol == "TCP"]


def who_uses(port: int, runner=subprocess.run) -> list[Listener]:
    return [l for l in listeners(runner, include_udp=True) if l.port == port]


def stop_refusal(listener: Listener) -> str:
    """Why this process must not be stopped, or ''."""
    if listener.pid in (0, 4) or listener.pid < 10:
        return "that's part of Windows itself"
    if listener.process.lower() in PROTECTED_NAMES:
        return f"{listener.process} is a Windows system process; stopping it can crash or log you out"
    if listener.pid == os.getpid():
        return "that's PortPilot itself"
    return ""


def stop(listener: Listener, force: bool = False, runner=subprocess.run) -> str:
    """Ask the process to close (taskkill /T); with force=True, end it (/F). Callers confirm with the user first."""
    reason = stop_refusal(listener)
    if reason:
        raise PermissionError(f"Not stopping PID {listener.pid}: {reason}.")
    command = ["taskkill", "/PID", str(listener.pid), "/T"] + (["/F"] if force else [])
    result = _run(command, runner)
    text = (_decode(result.stdout) + _decode(result.stderr)).strip()
    if result.returncode != 0:
        raise RuntimeError(text or f"taskkill failed ({result.returncode})")
    return text or f"Stopped PID {listener.pid}."


def free_port(start: int = 3000, end: int = 9999, host: str = "127.0.0.1") -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"no free port between {start} and {end}")


# ----------------------------------------------------------------------------- WSL
@dataclass
class Distro:
    name: str
    state: str
    version: str
    default: bool


def parse_wsl_list(text: str) -> list[Distro]:
    distros = []
    for line in text.splitlines():
        line = line.replace("\x00", "").rstrip()
        if not line.strip() or line.strip().upper().startswith("NAME"):
            continue
        default = line.lstrip().startswith("*")
        parts = line.replace("*", " ").split()
        if len(parts) >= 3:
            distros.append(Distro(" ".join(parts[:-2]), parts[-2], parts[-1], default))
    return distros


def wsl_distros(runner=subprocess.run) -> list[Distro]:
    try:
        result = _run(["wsl.exe", "-l", "-v"], runner)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_wsl_list(_decode(result.stdout)) if result.returncode == 0 else []


def wsl_action(action: str, distro: str = "", runner=subprocess.run) -> str:
    commands = {"stop": ["wsl.exe", "--terminate", distro], "shutdown": ["wsl.exe", "--shutdown"]}
    if action not in commands or (action == "stop" and not distro):
        raise ValueError("action must be 'stop' (with a distro) or 'shutdown'")
    result = _run(commands[action], runner, timeout=60)
    return _decode(result.stdout).strip() or ("Done." if result.returncode == 0 else _decode(result.stderr))


# ----------------------------------------------------------------------------- Docker
def docker_containers(runner=subprocess.run) -> list[dict] | None:
    """Running containers, or None when Docker isn't installed or not running."""
    try:
        result = _run(["docker", "ps", "--format", "{{json .}}"], runner)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    rows = []
    for line in _decode(result.stdout).splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        rows.append({"id": data.get("ID", ""), "name": data.get("Names", ""), "image": data.get("Image", ""),
                     "ports": data.get("Ports", ""), "status": data.get("Status", "")})
    return rows


def docker_stop(container: str, runner=subprocess.run) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container or ""):
        raise ValueError("not a container id or name")
    result = _run(["docker", "stop", container], runner, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(_decode(result.stderr).strip() or "docker stop failed")
    return f"Stopped {container}."


# ----------------------------------------------------------------------------- hosts file
HOSTS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts")


def parse_hosts(text: str) -> list[tuple[str, list[str], str]]:
    """(address, names, comment) for every active entry."""
    entries = []
    for line in text.splitlines():
        body, _, comment = line.partition("#")
        parts = body.split()
        if len(parts) >= 2:
            entries.append((parts[0], parts[1:], comment.strip()))
    return entries


def hosts_entries(path: str = HOSTS) -> list[tuple[str, list[str], str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return parse_hosts(handle.read())
    except OSError:
        return []


def edit_hosts_as_admin() -> None:
    """Opens the hosts file in Notepad with an administrator prompt (Windows asks the user)."""
    if sys.platform == "win32":
        subprocess.Popen(["powershell", "-NoProfile", "-Command",
                          f"Start-Process notepad.exe -ArgumentList '{HOSTS}' -Verb RunAs"], creationflags=NO_WINDOW)


def command_line(pid: int, runner=subprocess.run) -> str:
    """The full command line of a process (which script a python.exe is running), or ''."""
    if pid <= 4:
        return ""
    script = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"
    try:
        result = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], runner, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return _decode(result.stdout).strip()
