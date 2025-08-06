# Changelog

All notable changes to RF2K-TRAINER will be documented in this file.

## [Unreleased]
- Placeholder for upcoming changes

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

