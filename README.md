# ZeroTrace

Windows desktop app to optimize Roblox. Applies fast flag presets directly to your installation and blocks specific asset IDs by intercepting HTTPS traffic at the network level.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What it does

**Fast Flags** — Writes a `ClientAppSettings.json` file directly into the Roblox version folder with the flags from the selected preset. Includes an Apply button and a Restore Default button that removes the file. ZeroTrace auto-detects the version folder across the official Roblox launcher, Bloxstrap, and Voidstrap.

**Asset Blocker** — Adds a redirect to the Windows hosts file so that `assetdelivery.roblox.com` resolves to `127.0.0.1`, then starts a local HTTPS server on port 443 that presents a self-signed certificate for that domain. Roblox connects to the local server. If the requested asset ID is in the blocklist, it receives a 404. Otherwise the request is forwarded to the real Roblox CDN using the IP resolved before the redirect was added. Hosts file is restored automatically when the app closes.

**Presets** — Fast flags and blocked asset IDs are stored together in a single `.json` file. Includes a built-in "Blox Fruits" preset with 67 network/render flags and 11 blocked assets. Custom presets can be saved and deleted from inside the app.

---

## Requirements

- Windows 10 / 11
- Python 3.10 or higher — [python.org](https://python.org/downloads) (check "Add to PATH" during install)
- Roblox installed through any of the supported launchers

Python dependencies (`customtkinter` and `cryptography`) are installed automatically on first launch.

---

## Supported launchers

| Launcher | Fast Flags | Asset Blocker |
|---|---|---|
| Roblox (official) | Yes | Yes |
| Bloxstrap | Yes | Yes |
| Voidstrap | No* | Yes |

\* Voidstrap manages its own fast flags and overwrites `ClientAppSettings.json` every time it launches Roblox. Use Voidstrap's built-in Fast Flags panel for that instead. Asset Blocker works regardless.

---

## Installation

Download the ZIP from GitHub and extract it, or clone it:

```
git clone https://github.com/7Wolfer/ZeroTrace.git
```

Then double-click `ZeroTrace.bat`. A UAC prompt will appear — accept it. Administrator rights are required for the Asset Blocker (port 443 and hosts file). Fast Flags work without admin but the launcher requests it upfront for convenience.

On first run, missing packages are installed automatically. This may take a few seconds.

---

## First-time setup

### Fast Flags

1. Open ZeroTrace
2. Select the "Blox Fruits" preset from the sidebar (loaded by default)
3. Click **Apply Flags**
4. Close Roblox completely and reopen it

The flags are read by Roblox at startup, not while the game is running. You need to restart Roblox after applying.

If Roblox updates and creates a new version folder, click Apply Flags again — ZeroTrace always targets the most recently modified version folder.

### Asset Blocker

The Asset Blocker needs a locally generated CA certificate to be trusted by Windows so Roblox accepts the connection to the local server.

1. Go to the **Asset Blocker** tab
2. Click **Install CA Certificate**
3. Accept the UAC prompt
4. The status changes to "Certificate installed"
5. Enable the switch to start the blocker

This only needs to be done once. The certificate is generated on your machine and never sent anywhere.

---

## Daily usage

1. Double-click `ZeroTrace.bat` — accept UAC
2. Enable the Asset Blocker switch if you want asset blocking
3. Launch Roblox normally

Fast Flags stay written to disk — you do not need to reapply them every session unless Roblox updates. Asset Blocker must be running while you play since it intercepts traffic in real time.

---

## Project structure

```
ZeroTrace/
├── main.py              # Entry point, dependency install, UAC elevation
├── fast_flags.py        # Launcher detection, flag file write/delete
├── presets.py           # Preset load/save/delete
├── proxy.py             # Hosts file, cert generation, local HTTPS server
├── ui.py                # CustomTkinter interface
├── ZeroTrace.bat        # Launcher (no console window)
└── data/
    └── Blox Fruits.json # Built-in preset
```

User presets: `%APPDATA%\ZeroTrace\presets\`  
Generated certificates: `%APPDATA%\ZeroTrace\certs\`

---

## How the Asset Blocker works

```
Roblox DNS lookup: assetdelivery.roblox.com
        │
        ▼
hosts file returns 127.0.0.1
        │
        ▼
Roblox connects to local HTTPS server (port 443)
        │
        ├── Asset ID in blocklist?
        │         │
        │        YES ──► 404 Not Found
        │
        └── NO ──► Forward to real CDN (direct IP, bypasses hosts)
```

The real IP of `assetdelivery.roblox.com` is resolved before the hosts entry is added, so forwarding works without going through the redirect.

---

## Notes

- Closing ZeroTrace while the Asset Blocker is active will restore the hosts file and stop the server automatically.
- If ZeroTrace crashes unexpectedly with the blocker on, Roblox asset delivery will fail until the hosts entry is removed manually from `C:\Windows\System32\drivers\etc\hosts`.
- The visual effect of texture-related flags may vary between Roblox versions. Network flags (RakNet) are the main reason to use the Blox Fruits preset.

---

## License

MIT
