# Changelog

## 0.1.1 (2026-10-24)

Fixes from a code review.

- Stop looks the port up again first and refuses if a different program has it now: if the program had exited, Windows could have given its process number to another one.
- "Free port" checks netstat's list too, and IPv6 (`::1`), so it no longer suggests a port another program holds on 0.0.0.0 or `::1` (Vite and Node often do).

## 0.1.0 (2026-10-22)

- Listening TCP (and optionally UDP) ports with program, PID, reach (local or network), friendly labels for 35 common dev ports, and the command line on demand.
- Stop with confirmation (normal close, then force); Windows system processes are refused.
- WSL distro list, terminate and shutdown; running Docker containers and stop; hosts file view and edit as administrator; free-port finder.
- A command line and a window.
- Listening ports are recognised on Windows in any language (by their empty remote address, not the word LISTENING).
