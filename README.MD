# RF2K TRAINER

## Quick Start — Windows Installer (no Python, no Git)
> **Recommended for most users (Windows 10/11, 64-bit).**

**Before you begin:** skim all steps once. On the first run Windows **SmartScreen** may show “Windows protected your PC.”  
This is expected (the installer is **unsigned**). See **Step D**.

### A. Download
1. Open your browser and go to **Releases**:  
   https://github.com/tnxqso/rf2k-trainer/releases/latest
2. Under **Assets**, download **`RF2K-TRAINER_*_Setup.exe`**.

### B. Install
1. Double-click the downloaded installer.
2. Click **Next** and accept the default install folder — the installer chooses automatically:
   - **Admin install:** `C:\Program Files\RF2K-TRAINER`
   - **Per-user install:** `%LOCALAPPDATA%\Programs\RF2K-TRAINER`
3. (Optional) Tick **Create Desktop shortcut**.
4. Click **Install** → **Finish**.

### C. First launch
- Use the Start Menu shortcut: **RF2K-TRAINER → RF2K-TRAINER (Launcher)**  
  *(or the Desktop shortcut if you created one).*
- On first run the launcher will:
  - **not** create a fresh config
  - if `settings.example.yml` is present, it is copied to **`%LOCALAPPDATA%\RF2K-TRAINER\settings.yml`**
  - ensure a `logs\` folder in **`%LOCALAPPDATA%\RF2K-TRAINER\logs`**
+- Edit **`%LOCALAPPDATA%\RF2K-TRAINER\settings.yml`** and set:
- offer to open **Notepad** so you can edit settings:
    - **FlexRadio**: set `radio.host` (port usually `4992`), keep `type: flex`
    - **Hamlib rigctl**: set `radio.type: rigctl`, `rigctld_model`, and serial/host as needed
- Save the file and return to the launcher.

# D. Windows Defender & SmartScreen

Our Windows installer and EXE are currently **unsigned**. Unsigned apps built
with **PyInstaller** (a self‑extracting executable) are *common* in small open‑source
projects and can trigger extra checks from Windows security features. Typical
messages you may see:

- **“Security scan required”** — a quick cloud reputation scan for low‑prevalence files.
- **“Threats found / quarantined”** — a **heuristic** or “Potentially Unwanted” detection.
  These are frequently **false positives** for PyInstaller apps built by small projects.

> If you obtained the installer from this repository’s **Releases** page and you trust it,
> the alerts above are expected and do **not** mean the file is malicious.

---

## Why the builds are unsigned

This project is volunteer‑run. Shipping a signed Windows build requires a
publisher code‑signing certificate and ongoing admin/verification. We’ve chosen
to focus our effort on code quality and transparency rather than the certificate
process for now. You can still verify and run the software safely (see below).

---

## Safe‑use checklist

1. **Download only from the official page**
   - Releases: `https://github.com/tnxqso/rf2k-trainer/releases/latest`
   - Asset name: `RF2K-TRAINER_*_Setup.exe`

2. **Keep Defender enabled**
   - Do *not* disable real‑time protection globally. If Defender quarantines the
     installer, review the entry and allow it *once* (see next section).

3. **Prefer the built‑in updater when convenient**
   - The launcher menu item **“Check for updates”** downloads the installer to a
     temporary folder and runs it. If Defender quarantines it, see the steps below.
   - Alternatively, download the installer manually from the Releases page and run it.

---

## If Defender quarantines the installer

1. Open **Windows Security → Virus & threat protection → Protection history**.  
2. Click the **RF2K‑TRAINER_update_*.exe** entry → **Actions → Restore**.  
3. Click the same entry again → **Actions → Allow on device**.  
4. Re‑run the installer (either from the launcher update flow or the file you downloaded).

> Only allow files you trust and only from the official release page. Never add
> broad folder exclusions for convenience.

---

## Prefer source? Run without the installer

You can **inspect the code** and run directly from source as described in [Installation & Configuration](#installation--configuration) if that feels safer.

## Notes

- SmartScreen may still show **“Windows protected your PC”** for unsigned apps.
  Click **More info → Run anyway** if you trust the file.
- Corporate environments may block unsigned installers by policy; consult your
  IT guidelines if applicable.

### E. Daily use
Launch **RF2K-TRAINER (Launcher)** and use the menu:
- **1)** Full tuning (all enabled bands)  
- **2)** Show tuning info (segments per band)
- **3)** Tune specific band(s)  
- **4)** Run in debug mode 
- **5)** Clear old logs  
- **6)** Check for updates


### F. Upgrade

**Windows (installed via the Setup.exe) — recommended**

- Use the launcher menu **6) Check for updates**.  
  The app will query GitHub Releases and, if a newer version exists, start the
  Windows installer with the **same scope** you originally used:
  - **Per-user** (no UAC): `%LOCALAPPDATA%\Programs\RF2K-TRAINER`
  - **Machine-wide** (UAC): `C:\Program Files\RF2K-TRAINER`
- The installer runs unattended (very silent) and keeps your `settings.yml` and `logs\`.
- Update log (for troubleshooting):  
  `%LOCALAPPDATA%\Temp\RF2K-TRAINER_update.log`


### G. Uninstall
Windows **Settings → Apps → Installed apps → RF2K-TRAINER → Uninstall**.

> ℹ️ If you use the installer, **skip “General Requirements”** below.


## Table of Contents

- [Short Demo (Video)](#short-demo-video)
- [Why RF2K-TRAINER Exists](#why-rf2k-trainer-exists)
- [Introduction](#introduction)
- [Features](#features)
- [Supported Radios](#supported-radios)
- [Requirements](#requirements)
- [Installation & Configuration](#installation--configuration)
  - [General Requirements (All Platforms)](#️-general-requirements-all-platforms)
  - [Windows Installation (Step-by-step)](#-windows-installation-step-by-step)
  - [Linux / macOS Installation](#-linux--macos-installation)
  - [Configuration Overview](#️-configuration-overview)
  - [Example `radio:` Settings](#example-radio-settings)
  - [Setting Your IARU Region](#setting-your-iaru-region)
- [Usage](#usage)
  - [Examples](#examples)
  - [Arguments](#arguments)
  - [Full automatic tuning](#full-automatic-tuning)
  - [Tuning a single band](#tuning-a-single-band)
  - [Show band segments info without tuning](#show-band-segments-info-without-tuning)
  - [Recommended First Step](#recommended-first-step)
- [Real-World Tuning Time (Example)](#real-world-tuning-time-example)
- [Band Plan Overrides](#band-plan-overrides)
- [Windows Launcher, Recommended](#windows-launcher-how-you-should-start-the-app)
- [Debugging and Troubleshooting](#debugging-and-troubleshooting)
- [Upgrade Instructions](#upgrade-instructions)
- [Contributing](#contributing)
  - [How to Contribute](#how-to-contribute)
  - [How to Submit a Pull Request](#how-to-submit-a-pull-request)
  - [Code Style and Practices](#code-style-and-practices)
- [Project Independence](#project-independence)
- [License](#license)
- [Acknowledgments](#acknowledgments)
- [API Note: "Tune & Store"](#api-note-tune--store)
- [Useful Resources](#useful-resources)
- [Installing Hamlib (rigctl)](#installing-hamlib-rigctl)
- [Disclaimer](#disclaimer)

---

## Short Demo (Video)

<video src="https://github.com/user-attachments/assets/82b11ebf-c8e6-4de2-93b4-688a2936922d"
       controls
       width="840"
       muted
       playsinline>
</video>


- Length: ~1 minute 30 secs
- What you’ll see: `.bat` launcher → `--info` band summary → guided tuning on 60m


## Why RF2K-TRAINER Exists

The RF2K-S HF Power Amplifier requires tuning to be performed and stored for every fixed frequency segment across the HF bands. This design makes sense, once tuned, the amplifier will instantly recall the correct match whenever you're back on that frequency. But the process of populating all segments can be painfully repetitive.

If you've installed a new antenna, changed coax length, or moved the station, chances are you'll need to re-tune every band. That means:

- Manually setting your transceiver to multiple dozen center frequencies
- Transmitting a low-power carrier (typically in CW or RTTY)
- Pressing "Tune & Store" on the amplifier
- Repeating this for every segment of every band you care about

It's easy to lose track of where you were, or forget to tune the segments near the band edges. Even if you're organized, this is a time-consuming and error-prone process.

**RF2K-TRAINER solves this** by automating the *radio side* of the process: stepping through all relevant frequencies based on the IARU band plan, calculating exact segment centers as defined in the amplifier (not just approximate steps), and letting the operator focus on confirming that it's safe to tune.

You stay in control – the program waits for your confirmation after each step – but all the manual work with frequency dials and checklists is gone.

This tool is especially useful if:
- You want complete tuning coverage for all bands of interest
- You’ve made changes to antennas or operating location
- You want to save time while still respecting operating practices

RF2K-TRAINER works with both FlexRadio (via native API) and other transceivers via Hamlib (`rigctl`). With FlexRadio, drive power can also be set automatically, otherwise you'll be prompted to do it manually before starting.

No shortcuts, no blind transmissions – just a smarter way to handle a tedious job.

## Introduction

**RF2K-TRAINER** is a command-line utility that automates the frequency stepping and guidance required to tune the **RF2K-S HF Power Amplifier** across its fixed segment architecture.

Based on IARU band plans (Region 1, 2, or 3), it calculates the exact center frequencies used for memory storage in the amplifier and walks the operator through each tuning step with minimal risk of error.

The tool communicates directly with your transceiver (FlexRadio or Hamlib-compatible) and optionally with the RF2K-S HF Power Amplifier itself (to some extent), logging every step and ensuring tuning sessions are repeatable and complete.

It’s a controlled, deterministic approach that reduces guesswork, while still keeping you in charge of transmission and safety.

---

## Features

- Supports both **FlexRadio** (via native TCP API) and **Hamlib-compatible radios** (via `rigctld`)
- Automatically connects to FlexRadio or rigctld based on configuration
- Fetches and validates band segment limits from IARU band plans
- Supports IARU Region 1, 2 and 3 via `iaru_region_X.yml` files
- Allows per-band power and limit overrides in `settings.yml`
- Connects to RF2K-S HF Power Amplifier over HTTP to read status and switch to STANDBY mode
- Calculates segment midpoints and detects edge gaps
- Fully interactive loop for tuning each segment per band
- Safety validation for drive power and frequency settings
- Calculates tuning points at segment centers for optimal segment coverage
- Supports RF2K-S HF Power Amplifier fixed tuning segments
- Detects and tunes sub-segment gaps at band edges
- Logs debug output and tuner data to separate files in the `logs/` directory
- Cross-checks radio frequency with **RF2K-S `/data`** (truncated to kHz, no rounding) after each segment frequency change.
- Tuner CSV now also logs **drive_pwr** and **swr_final** (when PTT was auto-detected).
- Clear **PTT status cues** in the console:
  - **Green** “OK to key” hint when the trainer is waiting for you to transmit
  - **Red** “TX ACTIVE” banner while the carrier is detected
  - These appear only during **auto-PTT** flows and disappear automatically



## Supported Radios

> ⚠️ **rigctl is experimental**: currently verified only against **Hamlib Dummy (model 1)**.  
> Real-rig testers and PRs are welcome—see [Contributing](#contributing).

`rf2k-trainer` supports the following radio control interfaces:

- **FlexRadio** via native TCP/IP API (tested)
- **Hamlib (rigctl)** for other radios supporting CAT via rigctld (experimental)

> ⚠️ When using `rigctl`, drive power cannot be automatically set by this program. You must manually ensure your transceiver outputs the correct `drive_power` during tuning steps.

See [Installing Hamlib (rigctl)](#installing-hamlib-rigctl) below for setup instructions.

## Requirements

- Python 3.10+
- A supported transceiver:
  - **FlexRadio** (e.g. FLEX-6000 series) with SmartSDR TCP API, or
  - Any radio supported by **Hamlib** via `rigctld` (experimental support)
- RF2K-S HF Power Amplifier (optional) with web API enabled (version 0.9 or later)

---


## Installation & Configuration

This section guides you through installing RF2K-TRAINER and preparing your system to communicate with your radio and amplifier.

---

### ⚙️ General Requirements (All Platforms)

> ✅ If you installed via the **Windows Installer**, you can **skip this entire section**. 
> These general requirements are primarily for source installs (developers, Linux/macOS, or advanced Windows setups).

Before proceeding, ensure the following tools are installed:

- Python **3.10 or later**  
  [Download Python](https://www.python.org/downloads/)

- `pip` – Python package manager (usually included with Python)

- Git – used to clone the repository  
  [Download Git](https://git-scm.com/downloads)  
  ✅ During setup on Windows, choose the option:  
  **"Git from the command line and also from 3rd-party software"**

- **Hamlib** – Required if you are **not using FlexRadio**  
  [Download Hamlib from SourceForge](https://sourceforge.net/projects/hamlib/)

---


### 🪟 Windows Installation (Step-by-step)

If you're new to Python or Git, follow each step carefully:

#### 1. Install Git  
[https://git-scm.com/downloads](https://git-scm.com/downloads)

#### 2. Install Python 3.10+  
[https://www.python.org/downloads/](https://www.python.org/downloads/)  
✅ Check **"Add Python to PATH"** during installation

#### 3. (Optional) Install Hamlib (for non Flexradio users)  
FlexRadio users can skip this step.

- Download the Windows installer from:  
  [`Hamlib on SourceForge`](https://sourceforge.net/projects/hamlib/files/hamlib/)  
  Example file: `hamlib-w64-4.6.4.exe` (version may vary)

- Run the installer and accept the default installation folder, typically:  
  ```
  C:\Program Files\hamlib-w64-4.6.4
  ```

- ⚠️ Take note of this installation path — you’ll need to copy it into your `settings.yml` file.

  Example:
  ```yaml
  radio:
    type: rigctl
    auto_start_rigctld: true
    rigctld_path: 'C:\Program Files\hamlib-w64-4.6.4\bin\rigctld.exe'
    model: 3073 # For Icom IC-7300
    serial_port: COM4
  ```

- ℹ️ `rigctl.exe` will automatically be discovered in the same folder as `rigctld.exe`, no need to configure it separately.

> 📝 The file `README.w64-bin.txt` in the Hamlib installation directory contains extra instructions and troubleshooting notes specific to Windows users.

#### 4. Open PowerShell  
Press `Windows + R`, type `powershell`, press Enter

#### 5. Clone the Repository
```powershell
git clone https://github.com/tnxqso/rf2k-trainer.git
cd rf2k-trainer
```

#### 6. Install Python Dependencies
```powershell
pip install -r requirements.txt
```

#### 7. Create and Edit Configuration
```powershell
copy settings.example.yml settings.yml
notepad settings.yml
```
Then edit `settings.yml` to define:
- IARU region (1, 2, or 3)
- Radio type (`flex` or `rigctl`)
- IP or COM settings
- Enabled bands and drive power

---

### 🐧 Linux / macOS Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/tnxqso/rf2k-trainer.git
   cd rf2k-trainer
   ```

2. **Install Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create and Edit Configuration**
   ```bash
   cp settings.example.yml settings.yml
   nano settings.yml
   ```

---

### ⚙️ Configuration Overview

All configuration is done via a single file: `settings.yml`

- Defines your IARU region
- Selects which bands to tune
- Sets drive power per band (FlexRadio only)
- Configures radio interface (FlexRadio or Hamlib rigctl)
- Sets amplifier connection (RF2K-S HF Power Amplifier via HTTP)

⚠️ Do not modify other `.yml` files — they are used internally by the program.

---

### Example `radio:` Settings

#### ✅ FlexRadio
```yaml
radio:
  type: flex
  host: 192.168.20.100
  port: 4992
```

#### 🛠️ Hamlib / rigctl
```yaml
radio:
  type: rigctl
  auto_start_rigctld: true
  rigctld_path: '/usr/local/bin/rigctld'
  model: 3073  # For Icom IC-7300
  serial_port: "/dev/ttyUSB0"
```

> ⚠️ **Important Note:** When using `rigctl`, `tuning_power` **cannot be set automatically**. You must manually configure power level on your radio before tuning.

---

### Setting Your IARU Region

In `settings.yml`:
```yaml
defaults:
  iaru_region: 1
```

You may override `band_start`, `band_end`, and `drive_power` per band if needed — but be cautious when overriding band limits unless you understand the implications.

---

## Usage

```bash
python main.py [bands ...] [--debug] [--info] [--clear-logs]
```

### Examples

```bash
python main.py 20 40
python main.py 80m 160m --debug
python main.py --clear-logs
python main.py --info
```

### Arguments

- `bands` – One or more bands to tune (e.g., `20`, `40m`, `160m`). If omitted, all enabled bands from `settings.yml` are used.
- `--debug` – Enables debug logging
- `--info` – Shows band tuning info without performing tuning
- `--clear-logs` – Deletes old logs and exits program
- `--help` – Shows usage help
- `--version` – Displays program version

#### Windows update options (CLI)

- `--check-updates` — interactive check & install.  
  Prompts in the console, then launches the Windows installer silently.  
  (The launcher window will close once the installer starts.)

- `--check-updates-auto` — **check only** (non-interactive).  
  Exit code: `0` up-to-date, `1` newer available, `2` error.  
  Does **not** download or install.

## Full automatic tuning

```bash
python main.py
```

This runs interactive mode for all enabled bands.

### Tuning a single band

```bash
python main.py 20
python main.py 40m
```

Only tunes that band if it's enabled.

### Show band segments info without tuning

```bash
python main.py --info
```

---

### Recommended First Step

```bash
python main.py --info
```

This verifies that all segment alignment and tuning parameters are correct before tuning.

![Example: Band Info Output](./assets/images/band_info.png)


---

## Real-World Tuning Time (Example)

> 💡 Curious how long the tuning process takes?

In a real-world test, tuning all enabled bands **except 160m** and **only the lower half of 6m**, took **approximately 18 minutes**.  
This included several retunes on certain frequencies, since occasionally a second tuning pass produced better SWR results.

This is a representative example using a FlexRadio and RF2K-S HF Power Amplifier combo with segment logging enabled.

---

## Logged Data (CSV)

Each session writes a tuner CSV to `logs\tuning-results_<timestamp>.csv` with the following fields: `freq_kHz,segment_size_kHz,mode,setup,L_nH,C_pF,drive_pwr,swr_final`

- `drive_pwr` and `swr_final` are populated **only when PTT was auto-detected** for that segment.  
- In manual PTT mode, those two fields are left blank.


## Band Plan Overrides

You **can** override `band_start`, `band_end`, and `drive_power` for each band in your `settings.yml` file —  
however, changing `band_start` and `band_end` is **not recommended** unless you fully understand the implications.

> ⚠️ Note: `drive_power` settings only apply when using **FlexRadio**.  
> If you're using `rigctl`, you must manually configure your radio’s output power before tuning.

These values affect how tuning points are calculated, and improper overrides may result in incomplete coverage or inefficient tuning. Proceed with caution.

### Important:

The RF2K-S HF Power Amplifier uses **fixed frequency segments** for storing tuning data. These segment sizes and their exact center frequencies are hardcoded in the amplifier firmware and cannot be changed.

- Each band has a defined `segment_size` (e.g. 9 kHz on 80m) and a known `first_segment_center`.
- These segment centers **rarely align with the official IARU band edges**, but this tool calculates the optimal center-aligned tuning points automatically – no manual adjustment needed.
- You do **not** need to align `band_start` or `band_end` to any specific step or grid.

> **Why center tuning matters:**  
> RF2K-S HF Power Amplifier stores one tuning memory per segment. Tuning off-center may result in suboptimal coverage, and any new tuning within the same segment will overwrite previous values. This tool always tunes at the exact center of each segment to ensure best coverage and minimal conflicts.


### Example: 6m band from IARU file

```yaml
6m:
  band_start: 50000
  band_end: 52000
```

If you need to limit the band range, you may do so in `settings.yml`. A valid override could be:

```yaml
6m:
  enabled: true
  band_start: 50100
  band_end: 51900     # Any value >= band_start at least one segment size
```

### Summary

- `drive_power` is safe to override per band.
- `band_end` must be at least a segment size larger than `band_start`.
- You are on your own if you override these. Make sure you understand what you're doing or you risk incomplete or incorrect tuning coverage.


---


## Windows Launcher (how you should start the app)

The installer places a Start Menu shortcut **RF2K-TRAINER** that opens a simple menu.
This is the **recommended** way to run the tool on Windows. The launcher uses `%LOCALAPPDATA%\RF2K-TRAINER` as working directory, ensures `logs\` exists, and copies `settings.example.yml` to `settings.yml` on first run.


![Launcher Script Screenshot](./assets/images/launcher_script.png)

This script allows users to interact with RF2K-TRAINER without typing commands manually.

The launcher also includes **menu item 6 (Check for updates)** which pulls the latest GitHub release and upgrades in place while preserving your settings.


## Debugging and Troubleshooting

**Common issue:** `Configuration file not found: settings.yml`  
- Solution: copy **`settings.example.yml`** → **`settings.yml`** and edit it, then launch via **`rf2k-trainer.bat`**.

- Check your radio connection settings in `settings.yml`:
  - For **FlexRadio**, verify the correct IP address and port (default: `4992`)
  - For **rigctl**, confirm that `rigctld` is running and listening on the correct port

- If using **FlexRadio**, make sure only one SmartSDR client is connected at a time.

- Confirm that your **RF2K-S** amplifier is reachable on the network and running API version **0.9** or later.

- Run the tool in debug mode to see detailed output:

  ```bash
  python main.py --debug
  ```

  This enables verbose logging and can help identify misconfigurations or communication issues.

- All logs are saved automatically in the `logs/` directory:
  - **Debug logs** (general program output):  
    `logs/rf2k-trainer_<timestamp>.log`
  - **Tuner logs** (tuning results per segment):  
    `logs/tuning-results_<timestamp>.csv`

> 💡 If you're requesting support or reporting a bug, include both log files.  
> They are essential for reproducing and diagnosing problems.

## Upgrade Instructions

To upgrade RF2K-TRAINER to the latest version:

1. Pull the latest version from GitHub (or copy new files manually):
   ```bash
   git pull origin main
   ```

2. If dependencies have changed (check `requirements.txt`), update them:
   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Backup your YAML configuration file:
   - `settings.yml`

4. Run the program as usual:
   ```bash
   python main.py --info
   ```

> Tip: See [`CHANGELOG.MD`](./CHANGELOG.MD) for specific upgrade notes or breaking changes.

## Contributing

We welcome contributions from radio amateurs, developers, and testers of all experience levels.

### How to Contribute

There are several ways you can help improve this project:

- 🐞 **Report Bugs:** Found a bug or something not working as expected? Please open an issue describing the problem in detail.
- 💡 **Suggest Enhancements:** Have an idea for a new feature or improvement? We'd love to hear it — open a feature request on GitHub.
- 🧪 **Test and Validate:** Try the software with your own FlexRadio or RF2K-S HF Power Amplifier setup. Let us know what works, what doesn't, and where things can be improved.
- 🔧 **Contribute Code:** Found a bug and fixed it? Want to add support for more radios or features? Fork the repository and submit a pull request.
- 📚 **Improve Documentation:** Typos, clarifications, or new explanations are always welcome. Good documentation helps everyone.

### How to Submit a Pull Request

1. **Fork the repository** to your GitHub account.
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/rf2k-trainer.git
   cd rf2k-trainer
   ```
3. **Create a new branch** for your changes:
   ```bash
   git checkout -b my-feature
   ```
4. **Make your changes** and commit:
   ```bash
   git commit -am "Add my feature"
   ```
5. **Push your changes** to your fork:
   ```bash
   git push origin my-feature
   ```
6. **Open a pull request** on the main repository.

### Code Style and Practices

- Follow Python best practices and PEP8 style guidelines.
- Add docstrings and comments to explain non-obvious code.
- Test your changes thoroughly before submitting.
- Keep pull requests focused — small, targeted improvements are easier to review.

---

We're grateful for every contribution, large or small. Your help makes this project better for everyone!

---

## Project Independence

RF2K-TRAINER is an independent open-source project created by and for the amateur radio community.

This project is **not affiliated with**, **endorsed by**, or **officially supported by** RF-KIT, RF-POWER, FlexRadio Systems, or the Hamlib project.  
All product names and trademarks mentioned are the property of their respective owners and are used strictly for interoperability and reference purposes.

And yes — this software is completely **free**. We don’t want your money, beer, or even coffee.  
(Okay, we *like* coffee and red wine but the best way to show appreciation is to use the tool, share feedback, or tell a fellow ham about it!)


## License

RF2K-TRAINER is released under the [MIT License](https://opensource.org/licenses/MIT).  
You are free to use, copy, modify, and distribute the software, as long as the original license and copyright notice remain.

---

## Acknowledgments

- [FlexRadio Systems](https://www.flexradio.com/)
- [RF-Power RF2K-S](https://rf-kit.de/)
- [Hamlib Project](https://hamlib.github.io/) — for providing rig control support across many transceivers
- Contributors to SmartSDR, RFKit API, and amateur radio open source tools

---

## API Note: "Tune & Store"

Currently, the RF2K-S HF Power Amplifier requires **manual activation** of the **"Tune & Store"** function on the front panel during each tuning step.  
Unfortunately, the [RFKit API (v0.9)](https://rf-power.eu/wp-content/uploads/2024/12/RFKIT_api_doc_0_9_0.html) does **not** offer any way to trigger this action remotely or programmatically.

A formal feature request has been submitted to the RF-Kit development team to enable this capability via the API.  
We remain hopeful that a future firmware release will add support for fully automated tuning workflows — including remote activation of **"Tune & Store"** and a response indicating when tuning has completed and been stored.

> Note: In practice, a single tuning pass often yields acceptable results, but occasionally a second pass improves performance.  
> While some users prefer full manual control, a hybrid approach — automatic first, manual fine-tuning if needed — could offer the best of both worlds.

---
## Useful Resources

Here are some useful links and documentation references that may assist with integration, troubleshooting, and further development:

- 📘 [RFKIT API and SDK Documentation](https://rf-power.eu/wp-content/uploads/2024/12/RFKIT_api_doc_0_9_0.html)  
  Official API documentation for RF2K-S HF Power Amplifier control (v0.9)

- 📖 [RF2K-S User Manual (June 2025)](https://rf-power.eu/wp-content/uploads/2025/06/RF2K-S_User_Manual_EN_06_25.pdf)  
  Latest user manual for RF2K-S HF Power Amplifier, including front panel operation and memory concepts

- 🧠 [SmartSDR TCPIP API (FlexRadio)](https://github.com/flexradio/smartsdr-api-docs/wiki/SmartSDR-TCPIP-API)  
  Unofficial documentation of the FlexRadio TCP/IP API (used for CAT control)

- 🔧 [Hamlib rigctl Manual (CLI Reference)](https://manpages.debian.org/testing/hamlib-utils/rigctl.1.en.html)  
  Command-line usage and supported functionality for Hamlib's `rigctl` interface

- 📡 [Hamlib GitHub Repository](https://github.com/Hamlib/Hamlib)  
  Source code, issues, and contributions to the Hamlib library

- 📝 [IARU Band Plans (Region 1)](https://www.iaru-r1.org/band-plans/)  
  Official regional band plan references (Region 1 shown — others available)

- 🛠️ [SDR Command Line Tools](https://github.com/dl1ksv/smartsdr-cli)  
  Tools and inspiration for controlling FlexRadio via scripts


- 🛠️ [rigctl - Man Page](https://www.mankier.com/1/rigctl)  
  Control radio transceivers and receivers. rigctl accepts commands from the command line as well as in interactive mode if none are provided on the command line.

If you know of other valuable resources that should be listed here, feel free to submit a pull request or open an issue!

## Installing Hamlib (rigctl)

If you're not using a FlexRadio, `RF2K Trainer` supports other radios through Hamlib's `rigctld`.

To install Hamlib:

### On Debian/Ubuntu:

```bash
sudo apt install hamlib-utils
```

### On macOS (with Homebrew):

```bash
brew install hamlib
```

### On Windows:

1. Download pre-built binaries from: [https://sourceforge.net/projects/hamlib/](https://sourceforge.net/projects/hamlib/)
2. Run the installer and note the install path (e.g. `C:\Program Files\hamlib-w64-4.6.4`)
3. You do **not** need to modify your system `PATH`. Just point to the rigctld path in `settings.yml` as described in [Example `radio:` Settings](#example-radio-settings)

Example configuration:

```yaml
radio:
  type: rigctl
  auto_start_rigctld: true
  rigctld_path: 'C:\Program Files\hamlib-w64-4.6.4\bin\rigctld.exe'
  model: 3073  # For Icom IC-7300
  serial_port: COM4
```

### rigctld Autostart

You no longer need to manually start `rigctld`. If `auto_start_rigctld: true` is set in `settings.yml` as shown in [Example `radio:` Settings](#example-radio-settings), the RF2K Trainer will start `rigctld` automatically.


## Disclaimer

This software is provided **as is**, without warranty of any kind. You are solely responsible for verifying safe and correct operation of your equipment. The authors accept no liability for damage to radio hardware, amplifiers, antennas, or other connected systems due to misconfiguration or improper use of this software.

> ⚠️ **Warning:** This tool actively controls your radio and amplifier. During the tuning process, RF output is triggered automatically. If the program crashes or is interrupted, your transceiver may remain in transmit or tuning mode.  
> It is the **user's full responsibility** to monitor and manage the transmission state at all times.

> 📻 **Operator Responsibility:** You must ensure that your transmissions do not interfere with other radio traffic. Always verify that the selected frequency is clear before tuning, and never leave the process unattended unless you are fully aware of the implications.

Do not rely on this tool for unattended or automated transmission unless you fully understand its behavior, failure modes, and risks.
