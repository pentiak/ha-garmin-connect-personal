# Changelog

## Unreleased

### Added

- Sensors for the rest of the daily summary: average SpO2 and average respiration rate,
  and, disabled by default, the day's highest and lowest Body Battery, how much it charged
  and drained, the lowest and highest heart rate, the lowest and latest SpO2, and the
  lowest, highest and latest respiration rate.
- Weight sensor with the latest weight entry of the last year, and, disabled by default,
  BMI, body fat and the time of the weigh-in. Weight is fetched every hour.
- Last activity sensors with the name, start time and duration of the most recently started
  activity, and, disabled by default, its type, distance, calories and average heart rate.
  The last activity is fetched after each sync and every hour.

### Changed

- Requires aio-garmin-personal 0.4.0.

## 0.2.0 - 2026-11-08

### Added

- Sensors for the most recent night: sleep score, sleep duration, HRV last night and HRV
  status, and, disabled by default, deep, light and REM sleep, awake time and the weekly HRV
  average. They update after each watch sync.
- The sensors name Garmin as their data source ("Data provided by Garmin"), as Garmin's API
  brand guidelines require.

### Changed

- Requires aio-garmin-personal 0.3.0.

### Fixed

- Data that reaches Garmin for the day before after the first sync of the new day, such as an
  activity from another device, is now added to that day's statistics. The day before is
  checked again every hour until midnight.
- A day on which the device could not sync before midnight, for example because the watch did
  not reach the phone, now gets its total once the device syncs. Before, that day stayed at
  zero in the statistics, and the first hour of the next day was counted twice.

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
