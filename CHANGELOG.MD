# Changelog

All notable changes to RF2K-TRAINER will be documented in this file.

## [Unreleased]
- Placeholder for upcoming changes

## [v0.9.100] - 2025-08-09
### ⚠️ Breaking Changes
- Tuning flow is now **PTT‑driven**. The program detects transmit state from the radio and guides tuning while the carrier is present. This replaces the previous ENTER‑to‑continue loop.
- A **TX slice must be selected** in SmartSDR (`tx=1`) before starting; otherwise the run aborts with a clear error.
- Minor logging format changes (may affect scripts that parse logs).

### ✨ Added
- New **asynchronous FlexRadio client** with a background listener for `radio`, `interlock`, `transmit`, and `slice` status streams.
- Robust **sequence/ACK** handling for all TCP commands.
- **PTT detection** via `interlock.state` stream for safer, deterministic tuning.
- **Snapshot & restore** of TX‑slice mode, frequency, and power on connect/disconnect.
- Graceful shutdown that ensures TUNE is off and the previous state is restored.

### 🛠 Changed
- User prompts and instructions reworked for the PTT‑driven process, including an audible **beep** cue when it’s time to tune.
- More resilient socket I/O with timeouts and clearer error messages.
- Clearer logging of radio nickname/callsign and TX slice changes.

### 🐛 Fixed
- Race conditions where early status frames could be missed immediately after connect.
- Occasional response handling issues when multiple ACKs arrived back‑to‑back.

## [v0.9.003] - 2025-08-07
### ⚠️ Breaking Changes
- `settings.yml` structure has changed.  
  Please **copy and customize** a fresh `settings.yml` from `settings.example.yml`.
- New config key `auto_start_rigctld` introduced under the `radio` section.
  If enabled, the program will automatically start `rigctld` before connecting via rigctl.

### ✨ Added
- **Automatic rigctld startup support** – RF2K-TRAINER can now launch `rigctld` automatically based on configuration.
- Automatic validation of Hamlib rig model ID using `rigctl -l` before launching `rigctld`
- Dynamic parsing and printing of supported rig models if validation fails
- Logging now includes rig model name from rig list (e.g., “Icom IC-7300”) on startup
- Detailed safety warning for `rigctl` users, emphasizing **manual TX power responsibility**
- Enhanced `show_instructions()` to detect rigctl usage and display critical amplifier safety info
- Added fallback detection logic for `rigctl.exe` in the same directory as `rigctld.exe`
- Warnings added if rigctl does not return any model list or stdout is empty

### 🛠 Changed
- Replaced verbose stdout debug capture during model validation with simplified output
- Clarified TX behavior expectations for `rigctl` vs FlexRadio, and pending evaluation of HF output with PTT
- Improved structure and phrasing of safety and tuning procedure messages
- `start_tune()` in `rigctl_client.py` now uses PTT but pending further verification of actual HF output
- Placeholder for future use of CW keying instead of PTT to guarantee HF emission

### 🐛 Fixed
- Bug where valid rig model IDs (e.g., 1 for Dummy) were still reported as invalid due to incorrect parsing
- Model validation now works even if stdout contains headers or padded columns

## [v0.9.002] - 2025-08-06
### ⚠️ Breaking Changes
- `settings.yml` structure has changed.  
  Please **copy and customize** a fresh `settings.yml` from `settings.example.yml`.

### ✨ Added
- **Hamlib rigctl support** – You can now use `rf2k-trainer` with any rig supported by Hamlib's `rigctld`.
- New radio configuration section in `settings.yml` (`type: rigctl`)
- Rig model and connection now configurable for non-FlexRadio users
- `settings.example.yml` updated to show both FlexRadio and rigctl configurations
- Full setup documentation for Hamlib added to `README.MD`
- Support for `rigctld` port and host overrides

### 🛠 Changed
- Restructured installation instructions into "All Platforms", "Windows", and "Linux/macOS" sections
- Improved documentation clarity in `README.MD`, especially around tuning behavior and power settings
- Tuning power now explicitly stated to only apply to FlexRadio systems
- Clarified warnings about transmission and user responsibility in `Disclaimer`

### 🐛 Fixed
- Tuning segments now validate against band plan automatically
- More robust handling of unsupported or misconfigured radios

## [v0.9]
### Added
- CLI argument parsing using `argparse`
- Global `AppContext` to simplify parameter passing
- Automatic flag normalization (`20` → `20m`)
- `--version`, `--clear-logs`, `--info` flags
- Upgrade instructions in `README.MD`

### Changed
- Refactored `main()` to use `create_context()`
- Improved logger setup and imports

### Fixed
- Linter not recognizing `FlexRadioClient` in early import stages
- Runtime errors due to undefined variables in `main.py`
