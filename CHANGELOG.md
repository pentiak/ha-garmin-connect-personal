# Changelog

## Unreleased

### Added

- Sensors for the most recent night: sleep score, sleep duration, HRV last night and HRV
  status, and, disabled by default, deep, light and REM sleep, awake time and the weekly HRV
  average. They update after each watch sync.

### Changed

- Requires aio-garmin-personal 0.3.0.

## 0.1.0 - 2026-10-30

### Added

- Setup with a Garmin Connect Personal API key, reauthentication when Garmin rejects the key, and
  reconfiguration to replace a key before it expires.
- Sensors for the current day in the Garmin account's time zone: total, active and resting
  calories, steps, distance, floors climbed, intensity minutes, resting heart rate, average
  stress, Body Battery and the time of the last sync.
- Daily totals start a new long-term statistics cycle at Garmin's midnight. Data that syncs after
  midnight for the day before is added to that day's statistics.
- The entry is titled with the Garmin display name, or with the account holder's name when the
  display name was never set.
- Diagnostics, with the API key, account identifiers and activity details redacted.
