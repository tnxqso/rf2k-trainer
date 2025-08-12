# Changelog

All notable changes to RF2K-TRAINER will be documented in this file.

## [Unreleased]
- Placeholder for upcoming changes

## [v0.9.115] - 2025-08-12
### 🔁 Repository baseline after history reset
- The repository history was reset (squash/orphan re-init) to simplify the repo.
- **No functional changes** compared to pre-reset `v0.9.115`; this tag now serves as the clean baseline after the rewrite.
- Notes:
  - Older tags from the previous history may no longer be directly connected to the current `main`.
  - If you need the old history, use the archived backup/bundle kept outside this repo.

### ✨ Added
- **Windows EXE** build via GitHub Actions (PyInstaller one-file).
- **Launcher** `rf2k-trainer.bat` (menu): prefers the EXE if present, otherwise runs Python; only prints the exit code on failure.
- **First-run setup** in the launcher: creates `logs\`, generates `settings.yml` (copies `settings.example.yml` if present, otherwise writes a safe minimal default), and offers to open it in Notepad.
- **rigctl flow**: auto-start `rigctld` (if configured), early validation of model/serial port, instant **manual PTT** for Hamlib **Dummy** (model 1).
- Improved safety/procedure messaging, including a clear **manual TX power** warning for `rigctl`.

### 🛠 Changed
- PTT handling tightened: event-driven when supported; otherwise polling; quick capability probe; `ptt_supported = False` for Dummy.
- Banner is resilient: **`print_banner_safe()`** falls back cleanly when `pyfiglet`/fonts are missing or when `NO_FIGLET=1`.
- README updated with a **Windows EXE Quick Start**, SmartScreen note, and an explicit statement that `rigctl` is **experimental** and needs user reports.

### 🐛 Fixed
- EXE crash due to `pyfiglet.fonts` not being packaged — fonts are now bundled correctly.
- Indentation issues around amplifier setup; more robust cleanup/restore in `graceful_exit()`.
- rigctl: abstract-class instantiation and PTT polling stalls addressed.

### 📦 Packaging / Release
- CI builds EXE and runs a **non-interactive smoke test** (`--info`, `NO_FIGLET=1`).
- Release ZIP includes:
  - `rf2k-trainer.exe`, `rf2k-trainer.bat`
  - `settings.example.yml`, `README.md`, `CHANGELOG.md`, `LICENSE`
  - **Bandplan/data files**: `iaru_region_1.yml`, `iaru_region_2.yml`, `iaru_region_3.yml`, `rf2k_segment_alignment.yml`

### ⚠️ Notes
- **rigctl** is currently tested only against **Hamlib Dummy**. We need reports from real rigs (ideally from developers); behavior may require adjustments.

## Pre-reset highlights (for reference)
- [v0.9.100] - 2025-08-09 – PTT-driven tuning flow, SmartSDR TX slice requirement, async Flex client, snapshot/restore.
- [v0.9.003] - 2025-08-07 – `rigctld` auto-start support, model validation, clearer safety messages, improved docs.
- [v0.9.002] - 2025-08-06 – Initial Hamlib rigctl support and restructured installation docs.
- [v0.9] – CLI/argparse, global `AppContext`, `--version`, `--clear-logs`, `--info`.
