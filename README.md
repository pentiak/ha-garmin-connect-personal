# Garmin Connect Personal for Home Assistant

A Home Assistant integration that reads your Garmin Connect account through Garmin's official
[Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api): calories,
steps, distance, intensity minutes, resting heart rate, stress and Body Battery for the current
day.

It uses a Personal API key that you create in Garmin Connect. It does not use your Garmin
password and does not need multi-factor authentication codes.

This is not a Garmin product.

**Status:** in development; not released yet.

## Requirements

- Home Assistant 2026.10 or later.
- A Garmin Connect account with a Personal API key (Garmin Connect → Settings → Personal API
  Key). Garmin shows the key once, so copy it when you create it. Keys expire after the period
  you choose, between 30 days and one year.

## Installation

### HACS

1. In HACS, add `https://github.com/pentiak/ha-garmin-connect-personal` as a custom repository
   of type Integration.
2. Install **Garmin Connect Personal** and restart Home Assistant.

### Manual

Copy `custom_components/garmin_connect_personal` into the `custom_components` folder of your
Home Assistant configuration and restart Home Assistant.

## Setup

Settings → Devices & services → Add integration → **Garmin Connect Personal**, then paste the
Personal API key.

## Development

The client library lives in a separate repository,
[aio-garmin-personal](https://github.com/pentiak/aio-garmin-personal). Design, decisions and the
plan are in [docs/](docs/).

```shell
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pre-commit install
.venv/bin/pytest
.venv/bin/pre-commit run --all-files
.venv/bin/python -I script/gen_translations.py   # after editing strings.json
```

## License

Apache License 2.0.
