# Changelog — RF2K-TRAINER

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
