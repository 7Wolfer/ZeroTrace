# ZeroTrace

> Windows desktop app to optimize Roblox — apply fast flag presets and block specific assets via a local HTTPS proxy.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

### ⚡ Fast Flags
- Auto-detects your Roblox installation under `%LOCALAPPDATA%\Roblox\Versions\`
- Writes `ClientSettings\ClientAppSettings.json` with the flags from the active preset
- **Apply** and **Restore Default** buttons
- Live status indicator showing whether flags are currently active

### 🛡 Asset Blocker
- Local MITM proxy that intercepts HTTPS traffic to `assetdelivery.roblox.com`
- Blocked asset IDs receive a `404` response — everything else is forwarded normally
- Activates the Windows system proxy automatically when turned on, clears it on close
- Editable blocklist — changes apply instantly without restarting the proxy

### 🗂 Presets
- A single `.json` file stores fast flags + blocked asset IDs together
- Bundled preset: **Blox Fruits** (67 network/render flags + 11 blocked assets)
- Create, save, and delete your own custom presets

---

## Requirements

- Windows 10 / 11
- Python 3.10+
- Dependencies are installed automatically on first run:
  - [`customtkinter`](https://github.com/TomSchimansky/CustomTkinter)
  - [`cryptography`](https://cryptography.io)

---

## Installation

```bash
git clone https://github.com/7Wolfer/ZeroTrace.git
cd ZeroTrace
python main.py
```

No manual `pip install` needed — missing packages are detected and installed on launch.

---

## First-time setup (Asset Blocker)

The Asset Blocker intercepts HTTPS traffic using a local self-signed CA certificate.  
You only need to do this once:

1. Open the **Asset Blocker** tab
2. Click **Install CA Certificate**
3. Accept the UAC prompt (requires administrator rights)

To undo it at any time, click **Uninstall CA Certificate**.

> The certificate is generated locally on your machine and never leaves it.

---

## Project structure

```
ZeroTrace/
├── main.py           # Entry point
├── fast_flags.py     # Roblox path detection + flag file management
├── presets.py        # Preset load / save / delete
├── proxy.py          # MITM proxy + Windows registry proxy toggle
├── ui.py             # CustomTkinter UI
└── data/
    └── Blox Fruits.json   # Bundled preset
```

User presets are saved to `%APPDATA%\ZeroTrace\presets\`.  
Generated certificates are stored in `%APPDATA%\ZeroTrace\certs\`.

---

## How the proxy works

```
Roblox  ──CONNECT──►  ZeroTrace proxy (127.0.0.1:8888)
                              │
                    assetdelivery.roblox.com?
                         ┌────┴────┐
                        YES       NO
                         │         │
                  ID in blocklist?  Transparent tunnel
                    ┌────┴────┐
                   YES       NO
                    │         │
                  404    Forward to Roblox CDN
```

---

## License

MIT
