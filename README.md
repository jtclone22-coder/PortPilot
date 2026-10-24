# PortPilot

**"Port 3000 is already in use", solved in one click.** PortPilot shows every program listening on your Windows PC:
- **What it is:** the port, the program, and the full command line (so you know *which* `python.exe` it is).
- **Who can reach it:** this PC only, or the network.
- **What it usually is:** a friendly label such as "Vite dev server", "PostgreSQL" or "Ollama".

Open it in the browser, or stop it after confirming.

The same window shows your **WSL distros** (with a shutdown button), running **Docker containers**, and your **hosts file**, with a button to edit it as administrator.

- **Nothing to install.** It uses Windows' own tools (netstat, tasklist, taskkill, wsl) plus Docker if you have it.
- **Safe stops.** It always asks first. It refuses to stop Windows' own processes (System, svchost, lsass, explorer and others) and tries a normal close before a forced one.
- **Copy a free port** for your next dev server.

## Download

Get **PortPilot-0.1.1-windows.zip** from [Releases](../../releases/latest), unzip it anywhere and double-click **PortPilot.exe** in the PortPilot folder. Nothing to install, and no Python needed.

Windows may say "Windows protected your PC" because the app is new: click **More info**, then **Run anyway**.

Prefer Python? With Python 3.9 or newer, download this repository and run `py -m portpilot` in its folder.

## Command line

```
py -m portpilot ports              # listening ports (add a filter: ports vite)
py -m portpilot who 3000 --details # what's on 3000, with its command line
py -m portpilot stop 3000          # asks before stopping
py -m portpilot free               # a free port from 3000 up
py -m portpilot wsl --action shutdown
py -m portpilot docker
py -m portpilot hosts --edit
```

## Tests
```
py -m unittest discover -s tests
```

MIT License.

## More tools

Made by [jtclone22-coder](https://github.com/jtclone22-coder): more free Windows tools are on that profile, and paid ones (DevSweep, Overnight, AssetAtlas) are on [Gumroad](https://clonemaster152.gumroad.com).
