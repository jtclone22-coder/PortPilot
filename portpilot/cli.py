"""Command line: ports, who, stop, free, wsl, docker, hosts, gui."""
from __future__ import annotations

import argparse
import sys

from . import __version__, system


def cmd_ports(args) -> int:
    for item in system.listeners(include_udp=args.udp):
        if args.filter and args.filter.lower() not in f"{item.port} {item.process} {item.label}".lower():
            continue
        if not args.all and item.port >= 49152:  # Windows' dynamic range is mostly noise
            continue
        scope = "this PC" if item.local_only else "network"
        print(f"{item.protocol} {item.port:>5}  {scope:<8} pid {item.pid:<6} {item.process:<30} {item.label}")
    return 0


def cmd_who(args) -> int:
    found = system.who_uses(args.port)
    if not found:
        print(f"Nothing is using port {args.port}.")
        return 1
    for item in found:
        print(f"{item.protocol} {item.address}:{item.port}  pid {item.pid}  {item.process}")
        if args.details:
            print(f"   {system.command_line(item.pid)}")
    return 0


def cmd_stop(args) -> int:
    found = [l for l in system.who_uses(args.port) if l.protocol == "TCP"] or system.who_uses(args.port)
    if not found:
        print(f"Nothing is using port {args.port}.")
        return 1
    target = found[0]
    refusal = system.stop_refusal(target)
    if refusal:
        print(f"Not stopping {target.process} (pid {target.pid}): {refusal}.")
        return 1
    if not args.yes:
        answer = input(f"Stop {target.process} (pid {target.pid}) on port {args.port}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Left running.")
            return 0
    print(system.stop(target, force=args.force))
    return 0


def cmd_free(args) -> int:
    print(system.free_port(args.start))
    return 0


def cmd_wsl(args) -> int:
    if args.action:
        print(system.wsl_action(args.action, args.distro or ""))
        return 0
    distros = system.wsl_distros()
    for d in distros:
        print(f"{'*' if d.default else ' '} {d.name:<24} {d.state:<10} WSL {d.version}")
    if not distros:
        print("No WSL distributions found.")
    return 0


def cmd_docker(args) -> int:
    containers = system.docker_containers()
    if containers is None:
        print("Docker isn't installed or isn't running.")
        return 1
    for c in containers:
        print(f"{c['id']:<13} {c['name']:<28} {c['status']:<22} {c['ports']}")
    return 0


def cmd_hosts(args) -> int:
    if args.edit:
        system.edit_hosts_as_admin()
        print("Opening the hosts file in Notepad (Windows will ask for administrator permission).")
        return 0
    for address, names, comment in system.hosts_entries():
        print(f"{address:<16} {' '.join(names)}" + (f"   # {comment}" if comment else ""))
    return 0


def cmd_gui(args) -> int:
    from .gui import main as gui_main
    return gui_main()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="portpilot", description="What's running on which port, and more.")
    parser.add_argument("--version", action="version", version=f"PortPilot {__version__}")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("ports", help="listening ports and their programs")
    p.add_argument("filter", nargs="?")
    p.add_argument("--udp", action="store_true")
    p.add_argument("--all", action="store_true", help="include Windows' dynamic ports (49152+)")
    p.set_defaults(func=cmd_ports)
    p = sub.add_parser("who", help="what is using PORT")
    p.add_argument("port", type=int)
    p.add_argument("--details", action="store_true", help="show the full command line")
    p.set_defaults(func=cmd_who)
    p = sub.add_parser("stop", help="stop the program using PORT (asks first)")
    p.add_argument("port", type=int)
    p.add_argument("--yes", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_stop)
    p = sub.add_parser("free", help="print a free port")
    p.add_argument("--start", type=int, default=3000)
    p.set_defaults(func=cmd_free)
    p = sub.add_parser("wsl", help="WSL distros; --action stop|shutdown")
    p.add_argument("--action", choices=["stop", "shutdown"])
    p.add_argument("--distro")
    p.set_defaults(func=cmd_wsl)
    sub.add_parser("docker", help="running Docker containers").set_defaults(func=cmd_docker)
    p = sub.add_parser("hosts", help="hosts file entries; --edit opens it as administrator")
    p.add_argument("--edit", action="store_true")
    p.set_defaults(func=cmd_hosts)
    sub.add_parser("gui", help="open the window").set_defaults(func=cmd_gui)
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        return cmd_gui(args)
    try:
        return args.func(args)
    except (PermissionError, RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
