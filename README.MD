# RF2K TRAINER

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-green.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#)

*A command-line tool to automatically tune your RF2K-S amplifier across HF band segments using region-specific band plans.*

---

## Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
  - [Windows Installation](#windows-installation)
  - [Linux/macOS Installation](#linuxmacos-installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Real-World Tuning Time (Example)](#real-world-tuning-time-example)
- [Band Plan Overrides](#band-plan-overrides)
- [Debugging and Troubleshooting](#debugging-and-troubleshooting)
- [Upgrade Instructions](#upgrade-instructions)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)
- [API Note: "Tune & Store"](#api-note-tune--store)
- [Useful Stuff](#useful-stuff)
- [Disclaimer](#disclaimer)

---

## Introduction

**RF2K TRAINER** is a command-line tool designed to automate the pre-tuning process of your **RF2K-S** solid-state amplifier across the HF amateur radio bands. It currently supports **FlexRadio** devices, but future versions aim to support a broader range of radios via common control interfaces.

The tool leverages standardized IARU band plans (Region 1, 2, or 3) to calculate precise tuning points across each band. You may optionally override band limits and tuning power settings on a per-band basis through a simple YAML configuration.

For each frequency segment, the program sets your radio accordingly and guides you through manual Tune & Store activation on the amplifier, streamlining what would otherwise be a time-consuming manual process.

---

## Features

- Automatically connects to FlexRadio via TCP using SmartSDR API
- Fetches and validates band segment limits from IARU band plans
- Supports IARU region 1, 2 and 3 via `iaru_region_X.yml` files
- Allows per-band power and limit overrides in `settings.yml`
- Connects to RF2K-S over HTTP to read status and switch to STANDBY mode
- Calculates segment midpoints, detects edge gaps
- Fully interactive loop for tuning each segment per band
- Safety validation for tuning power and frequency settings
- Supports RF2K-S fixed tuning segments
- Calculates tuning points at segment centers for maximum reuse
- Detects and tunes sub-segment gaps at band edges
- Logs debug output and tuner data to separate files in `logs/` directory

## Requirements

- Python 3.10+
- A FlexRadio device (e.g. FLEX-6000 series) accessible on LAN or VPN
- RF2K-S amplifier (optional) with web API enabled (v0.9)

---

## Installation

### ⚠️ Requirements (All Platforms)

- Python **3.10 or later**  
  [Download from python.org](https://www.python.org/downloads/)
- `pip` (Python package manager) — usually installed with Python  
- [Git](https://git-scm.com/downloads) (for cloning the repository)  
  On Windows, choose the **"Git from the command line and also from 3rd-party software"** option during installation.

---

### 🪟 Windows Installation (Step-by-step)

If you're new to Git or Python, follow these steps carefully:

1. **Install Git**  
   Download and install from [git-scm.com](https://git-scm.com/downloads)

2. **Install Python 3.10+**  
   Download from [python.org](https://www.python.org/downloads/)  
   ✅ **Important**: During installation, check **"Add Python to PATH"**

3. **Open PowerShell**  
   Press `Windows` + `R`, type `powershell`, then press `Enter`.

4. **Download the Project**

```powershell
git clone https://github.com/tnxqso/rf2k-trainer.git
cd rf2k-trainer
```

5. **Install Python Dependencies**

```powershell
pip install -r requirements.txt
```

6. **Create Your Settings File**

```powershell
copy settings.example.yml settings.yml
notepad settings.yml
```

👉 Edit the file in Notepad and fill in:
- Your IARU region (1, 2 or 3)
- Your FlexRadio host address
- Enable the bands you want to tune

---

### 🐧 Linux / macOS Installation

1. Clone the repository:

```bash
git clone https://github.com/tnxqso/rf2k-trainer.git
cd rf2k-trainer
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy and edit the settings file:

```bash
cp settings.example.yml settings.yml
nano settings.yml
```

Edit `settings.yml` to match your IARU region, FlexRadio IP, and desired band settings.


---

## Configuration

The configuration is split into:

- `settings.yml`: Main configuration including enabled bands, tuning power, FlexRadio and RF2K-S host settings
- `iaru_region_1.yml`, etc: Read-only band limits per IARU region

Specify the region using:

```yaml
defaults:
  iaru_region: 1
```

Each band can be enabled, disabled, or override power and band limits if necessary.

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

This is a representative example using a FlexRadio and RF2K-S combo with segment logging enabled.

---


## Band Plan Overrides

You **can** override `band_start`, `band_end`, and `tune_power` for each band in your `settings.yml` file – but overriding `band_start` and `band_end` is **not recommended** unless you fully understand the consequences.

### Important:

The RF2K-S amplifier uses **fixed frequency segments** for storing tuning data. These segment sizes and their exact center frequencies are hardcoded in the amplifier firmware and cannot be changed.

- Each band has a defined `segment_size` (e.g. 9 kHz on 80m) and a known `first_segment_center`.
- These segment centers **rarely align with the official IARU band edges**, but this tool calculates the optimal center-aligned tuning points automatically – no manual adjustment needed.
- You do **not** need to align `band_start` or `band_end` to any specific step or grid.

> **Why center tuning matters:**  
> RF2K-S stores one tuning memory per segment. Tuning off-center may result in suboptimal coverage, and any new tuning within the same segment will overwrite previous values. This tool always tunes at the exact center of each segment to ensure best coverage and minimal conflicts.


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

- `tune_power` is safe to override per band.
- `band_end` must be at least a segment size larger than `band_start`.
- You are on your own if you override these. Make sure you understand what you're doing or you risk incomplete or incorrect tuning coverage.


---


## Windows Launcher Script (Optional)

To simplify usage for less technical users, RF2K-TRAINER includes a ready-to-use `.bat` launcher script that presents a text-based menu of common options:

![Launcher Script Screenshot](./assets/images/launcher_script.png)

This script allows users to interact with RF2K-TRAINER without typing commands manually.

### Create a Desktop Shortcut

You may create a shortcut to the launcher for easier access:

1. Locate the `rf2k-trainer.bat` file inside your `rf2k-trainer` folder (typically under `C:\Users\YourName\rf2k-trainer`)
2. Right-click the file and choose **Send to → Desktop (create shortcut)**
3. (Optional) Right-click the new shortcut and choose **Properties**
   - Under the **Shortcut** tab, you may choose **Change Icon** to give it a custom look
   - You can also set it to **Run: Minimized** if preferred
4. Double-click the icon to launch RF2K-TRAINER

This is the recommended way to run RF2K-TRAINER on Windows for casual or non-technical users.


## Debugging and Troubleshooting

- Verify your FlexRadio IP address and port in `settings.yml` (default: `4992`)
- Make sure only one SmartSDR client is connected to the radio at a time
- Ensure your RF2K-S amplifier is accessible and running API version **0.9** or later
- You can run the program with the `--debug` flag to enable verbose output:

  ```bash
  python main.py --debug
  ```

  This provides more insight into the steps being executed and may help identify misconfiguration or communication issues.

- Logging to file is **not yet implemented**, but will be added in a future release.

- All debug and amplifier interaction logs are saved in `logs/rf2k-trainer<TIMESTAMP>.log`
- Tuner data (segment tuning results) are written to CSV files in `logs/` after each tuning pass
- Include both log types when requesting help — they are critical for reproducing issues

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
- 🧪 **Test and Validate:** Try the software with your own FlexRadio or RF2K-S setup. Let us know what works, what doesn't, and where things can be improved.
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

This project is **not affiliated with**, **endorsed by**, or **officially supported by** RF-KIT, RF-POWER, or FlexRadio Systems.  
All product names and trademarks mentioned are the property of their respective owners and are used strictly for interoperability and reference purposes.



## License

MIT License

---

## Acknowledgments

- [FlexRadio Systems](https://www.flexradio.com/)
- [RF-Power RF2K-S](https://rf-kit.de/)
- Contributors to SmartSDR, RFKit API, and amateur radio open source tools

---

## API Note: "Tune & Store"

At this time, the RF2K-S amplifier requires the user to press the **"Tune & Store"** button manually on the front panel during tuning. [The RFKit API (v0.9)](https://rf-power.eu/wp-content/uploads/2024/12/RFKIT_api_doc_0_9_0.html) does not support triggering this action programmatically.

A feature request has been submitted to the RF-Kit development team to add API support for automating **Tune & Store**. We hope this functionality will become available in a future firmware update.

---
## Usfeul Stuff
- [RFKIT API and SDK Documentation](https://rf-power.eu/wp-content/uploads/2024/12/RFKIT_api_doc_0_9_0.html)
- [RF2K-S User Manual](https://rf-power.eu/wp-content/uploads/2025/06/RF2K-S_User_Manual_EN_06_25.pdf)
- [SmartSDR TCPIP API](https://github.com/flexradio/smartsdr-api-docs/wiki/SmartSDR-TCPIP-API)

## Disclaimer

This software is provided **as is**, without warranty of any kind. You are solely responsible for verifying safe and correct operation of your equipment. The authors accept no liability for damage to radio hardware, amplifiers, antennas, or other connected systems due to misconfiguration or improper use of this software.

Do not rely on this tool for unattended or automated transmission unless you fully understand its implications and risks.
