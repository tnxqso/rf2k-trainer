# Changelog

All notable changes to RF2K-TRAINER will be documented in this file.

## [Unreleased]
- Placeholder for upcoming changes

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

