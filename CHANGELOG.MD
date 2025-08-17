# Changelog

All notable changes to RF2K-TRAINER will be documented in this file.

## [Unreleased]
- Placeholder for upcoming changes

## [v0.9.313] - 2025-08-17
### ✨ Added
- **Windows updater** (`updater.py`) integrated:
  - `--check-updates` = interactive flow (asks **Y/n**, downloads, starts installer silently).
  - `--check-updates-auto` = **check only** (no download/install). Returns exit code **0** (up-to-date), **1** (newer available), **2** (error).
  - Uses the **existing install scope** automatically: *per‑user* (no UAC) when installed under LocalAppData, or *machine‑wide* (UAC) when installed under Program Files.
  - Writes Inno Setup log to **`%TEMP%\RF2K-TRAINER_update.log`** and exits the trainer with code **111** when the installer is launched so the launcher can close.
  - Clearer status lines (always show `v`-prefix): e.g. *`[update] up to date: v0.9.313 (latest release: v0.9.312)`*.

### 🛠 Changed
- **Launcher (`rf2k-trainer.bat`)**
  - Menu item **6. Check for updates** calls `--check-updates`; the window now pauses so users can read the update messages before it closes.
  - Better state-dir handling and first‑run setup are kept; EXE is preferred over source.
- **Build/Packaging**
  - **Custom app icon** is now embedded in the EXE via PyInstaller (`--icon assets\icons\rf2k-trainer.ico`) and used for the installer (`SetupIconFile=..\assets\icons\rf2k-trainer.ico`).
  - **Shortcuts**: when a `.bat` launcher is present, shortcuts point to the BAT but use the EXE’s icon so the custom icon displays correctly.

### 🐛 Fixed
- **Clear logs**: selecting **5. Clear old logs** now only clears logs and returns to the menu (no unintended full tuning run).
- Robust quoting for installer arguments/log path (fixes “filename/label syntax” errors on some systems).

## [v0.9.300] - 2025-08-16
### ⚠️ Breaking Changes
- **Release packaging change (Windows):** GitHub Releases now publish **only** the Windows
  **Installer** (`RF2K-Trainer_Setup_vX.Y.Z.exe`). The standalone one-file EXE and the portable
  ZIP are no longer attached. Developers can still build a portable EXE locally via the workflow or
  PyInstaller.

### ✨ Added
- **Windows Installer (Inno Setup):** One-click install with Start Menu shortcuts, optional Desktop
  shortcut, and a proper Uninstaller. Installs the EXE, launcher BAT, data files, and README. First-run
  still creates `settings.yml` and `logs\` if missing.
- **Application/installer icon:** custom `.ico` embedded in both the EXE and the Installer.
- **Single-instance launcher:** `rf2k-trainer.bat` now prevents multiple concurrent sessions using
  a PID lock file and auto-cleans stale locks.

### 🛠 Changed
- **Launcher UX:** always runs from its own directory, warns (non-blocking) if not in the recommended
  folder, prefers local EXE, then EXE in the recommended folder, else falls back to `python main.py`.
  Prints exit code only on failure.
- **CI pipeline:** On tag pushes (`v*`) or manual dispatch, build one-file EXE (bundling `pyfiglet` fonts),
  run a non-interactive smoke test (`--info`, copies `settings.example.yml` → `settings.yml`, `NO_FIGLET=1`),
  then compile the **Inno Setup** installer. **Only the installer** is attached to the Release asset list
  (GitHub still auto-adds “Source code (zip/tar.gz)”).
- **Docs:** README updated to emphasize the Windows Installer Quick Start and that “General requirements”
  do not apply to the installer path. Mentioned the demo video and recommended using the launcher/Start Menu.

### 🐛 Fixed
- More robust first-run config creation and clearer messages in the launcher.
- Minor polishing around exit handling and path checks.

## [v0.9.202] - 2025-08-15
### ⚠️ Breaking Changes
- **New RF2K-S setting:** `rf2k_s.interface` (default `CAT`).  
  The trainer now decides when it’s meaningful to verify frequency against the
  RF2K-S API based on this setting. Allowed values: `CAT`, `UNIV`, `UDP`, `TCI`.  
  **Action:** add in your `settings.yml`:
  ```yaml
  rf2k_s:
    interface: CAT
  ```

### ✨ Added
- **Visual PTT cues (ANSI colors):**  
  - **Green banner** when auto-PTT is armed: “AUTO-PTT READY — press PTT…”.  
  - **Red banner** while transmitting: “TX ACTIVE — tune & store, then UNKEY”.  
  Banners auto-hide when they become irrelevant; no full-screen clears.
- **Frequency verification policy:**  
  `/data` frequency check now runs **only** when `rf2k_s.interface` is `CAT`
  **and** the radio is **not** Hamlib **Dummy**.

### 🛠 Changed
- **/data frequency mismatch is now fatal:** truncated-kHz mismatch aborts the
  run with a clear **[FATAL]** and non-zero exit code.
- **Tuning loop cleanup:** helper moved to module scope; uniform behavior for
  event-PTT and polling-PTT. Manual mode skips verification.
- **Cleaner UX:** in event-PTT mode, progress “dots” are suppressed in favor of
  the colored banners. Polling mode keeps dots but remains concise.

### 🐛 Fixed
- Spurious `/data` mismatches on Hamlib **Dummy** are avoided by skipping
  verification when no RF-based update is possible.
- Bounded wait windows reduce timing edge cases in frequency checks.

### 📋 Notes
- **Hamlib/rigctl is still experimental.** Tested against **Hamlib Dummy** only.
  Real-rig reports (and focused PRs) are welcome.
- Post-UNKEY `/power` read from v0.9.201 remains: logs `drive_pwr` and
  `swr_final` when auto-PTT was used (blank for manual).

## [v0.9.201] - 2025-08-14
### ✨ Added
- **RF2K-S `/data` frequency verification** after setting segment frequency: compares PA-reported frequency (truncated to kHz, no rounding) with the radio’s set value, with bounded retries.
- **Post-unkey PA snapshot** via `/power`: a single read **0.2 s** after UNKEY (2.0 s timeout, no retries) to capture **`swr_final`** and **`drive_pwr`** for the segment.

### 🛠 Changed
- **CSV logging moved into the client**: `rf2ks_logger.py` removed; CSV logging now lives in `RF2KSClient.log_tuner_data()`.
- `log_tuner_data()` now:
  - always logs tuner state from `/tuner`;
  - when **auto-PTT** was used, it internally calls `/power` once and appends `drive_pwr` and `swr_final`;
  - when **manual PTT** was used, the two new columns are left blank.
- `main.py`: tuning loop now passes `used_auto_ptt` to `rf2ks.log_tuner_data(...)`; no `/power` calls from `main` anymore.

### 📦 CI / Packaging
- Windows build workflow now **runs on tag pushes only** (`v*`) and `workflow_dispatch`.
- Smoke test copies `settings.example.yml` → `settings.yml` before running `--info`, disables FIGLET in CI, and fails hard if the EXE is missing.
- Release ZIP still bundles all required data files (`iaru_region_{1,2,3}.yml`, `rf2k_segment_alignment.yml`) plus the launcher BAT.

### 🐛 Fixed
- Avoid spurious mismatches by **truncating to kHz** for `/data` frequency comparisons (matches the RF2K-S front-panel display behavior).
- Ensure CSV header is written exactly once even after refactor (no duplicate headers).

### ⚠️ Notes
- **Hamlib/rigctl remains experimental** — currently verified only against **Hamlib Dummy** (model 1). Real-rig reports (and PRs) are very welcome.
- API load remains low: at most one `/power` request per segment **only** when auto-PTT was detected.


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
