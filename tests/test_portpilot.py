"""PortPilot tests: parsers on sample output, and stop() against a fake runner (nothing real is stopped)."""
from __future__ import annotations

import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portpilot import system  # noqa: E402

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1012
  TCP    127.0.0.1:5173         0.0.0.0:0              LISTENING       8840
  TCP    127.0.0.1:5173         127.0.0.1:61234        ESTABLISHED     8840
  TCP    0.0.0.0:3000           0.0.0.0:0              LISTENING       9001
  TCP    [::]:3000              [::]:0                 LISTENING       9001
  TCP    [fe80::1%12]:7680      [::]:0                 LISTENING       4
  UDP    0.0.0.0:5353           *:*                                    2210
"""
TASKLIST = '"svchost.exe","1012","Services","0","12,000 K"\n"node.exe","8840","Console","1","90,000 K"\n' \
           '"python.exe","9001","Console","1","40,000 K"\n"chrome.exe","2210","Console","1","1 K"\n'


class FakeRun:
    def __init__(self, outputs: dict, returncode: int = 0):
        self.outputs, self.returncode, self.calls = outputs, returncode, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)

        class Result:
            pass

        result = Result()
        result.returncode = self.returncode
        result.stdout = self.outputs.get(command[0], b"")
        result.stderr = b""
        return result


class ParserTests(unittest.TestCase):
    def test_netstat_and_tasklist(self) -> None:
        found = system.parse_netstat(NETSTAT)
        self.assertEqual([(l.protocol, l.address, l.port, l.pid) for l in found], [
            ("TCP", "0.0.0.0", 135, 1012), ("TCP", "0.0.0.0", 3000, 9001), ("TCP", "::", 3000, 9001),
            ("TCP", "127.0.0.1", 5173, 8840), ("UDP", "0.0.0.0", 5353, 2210), ("TCP", "fe80::1", 7680, 4)])
        self.assertEqual(system.parse_tasklist(TASKLIST)[8840], "node.exe")

    def test_listeners_join_names_and_labels(self) -> None:
        fake = FakeRun({"netstat": NETSTAT.encode(), "tasklist": TASKLIST.encode()})
        found = system.listeners(fake)
        vite = next(l for l in found if l.port == 5173)
        self.assertEqual((vite.process, vite.label, vite.local_only), ("node.exe", "Vite dev server", True))
        self.assertTrue(all(l.protocol == "TCP" for l in found))
        self.assertEqual(next(l for l in found if l.port == 7680).process, "System")
        self.assertEqual(vite.browser_url, "http://localhost:5173/")

    def test_wsl_list_is_utf16(self) -> None:
        text = "  NAME            STATE           VERSION\r\n* Ubuntu-22.04    Running         2\r\n  docker-desktop  Stopped  2\r\n"
        distros = system.parse_wsl_list(system._decode(text.encode("utf-16-le")))
        self.assertEqual([(d.name, d.state, d.version, d.default) for d in distros],
                         [("Ubuntu-22.04", "Running", "2", True), ("docker-desktop", "Stopped", "2", False)])

    def test_hosts(self) -> None:
        entries = system.parse_hosts("# comment\n127.0.0.1 localhost dev.local  # mine\n\n::1 localhost\n")
        self.assertEqual(entries, [("127.0.0.1", ["localhost", "dev.local"], "mine"), ("::1", ["localhost"], "")])

    def test_docker(self) -> None:
        line = b'{"ID":"abc123","Names":"db","Image":"postgres:16","Ports":"0.0.0.0:5432->5432/tcp","Status":"Up 2 hours"}\n'
        self.assertEqual(system.docker_containers(FakeRun({"docker": line}))[0]["name"], "db")
        self.assertIsNone(system.docker_containers(FakeRun({}, returncode=1)))
        with self.assertRaises(ValueError):
            system.docker_stop("db; rm -rf /")


class StopTests(unittest.TestCase):
    def test_refuses_windows_processes(self) -> None:
        for listener in (system.Listener("TCP", "0.0.0.0", 445, 4, "System"),
                         system.Listener("TCP", "0.0.0.0", 135, 1012, "svchost.exe"),
                         system.Listener("TCP", "0.0.0.0", 135, 900, "LSASS.EXE")):
            self.assertTrue(system.stop_refusal(listener))
            with self.assertRaises(PermissionError):
                system.stop(listener, runner=FakeRun({}))

    def test_stop_uses_taskkill(self) -> None:
        fake = FakeRun({"taskkill": b"SUCCESS: Sent termination signal to process with PID 8840."})
        message = system.stop(system.Listener("TCP", "127.0.0.1", 5173, 8840, "node.exe"), runner=fake)
        self.assertEqual(fake.calls[-1], ["taskkill", "/PID", "8840", "/T"])
        self.assertIn("SUCCESS", message)
        system.stop(system.Listener("TCP", "127.0.0.1", 5173, 8840, "node.exe"), force=True, runner=fake)
        self.assertEqual(fake.calls[-1][-1], "/F")
        with self.assertRaises(RuntimeError):
            system.stop(system.Listener("TCP", "127.0.0.1", 5173, 8840, "node.exe"), runner=FakeRun({}, returncode=128))

    def test_free_port_skips_a_taken_one(self) -> None:
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            port = taken.getsockname()[1]
            taken.listen(1)
            self.assertNotEqual(system.free_port(port, port + 50), port)


if __name__ == "__main__":
    unittest.main()
