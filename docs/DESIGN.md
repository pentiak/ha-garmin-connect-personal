# Design

A Home Assistant integration that reads a Garmin Connect account through Garmin's
[Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api), and the
async client library it depends on. The goal is the Platinum tier of Home Assistant's
[integration quality scale](https://contributors.home-assistant.io/core/quality-scale/rules/),
first distributed through HACS and later submitted to Home Assistant core.

Decisions and their reasons are in [DECISIONS.md](DECISIONS.md). Work still to do is in
[PLAN.md](PLAN.md).

## Components

```
Garmin Personal API ──HTTPS──▶ aio-garmin-personal ──▶ garmin_connect_personal (HA integration)
                                (PyPI library)            coordinator ─▶ sensors
```

| Component | Repository | Role |
|---|---|---|
| `aio-garmin-personal` | `pentiak/aio-garmin-personal` | All HTTP: key-to-token exchange, requests, response parsing, error mapping. No Home Assistant imports. |
| `garmin_connect_personal` | `pentiak/ha-garmin-connect-personal` | Config flow, coordinator, entities. No HTTP code; everything goes through the library. |

Home Assistant requires this split for core integrations (rule `dependency-transparency`, and
the core checklist rule that integrations contain no protocol code).

## The Personal API

The facts the design depends on. Sources: Garmin's OpenAPI document (kept in
`../reference/`, see DECISIONS.md ADR-0014), Garmin's Python client
`garmin/connect-personal-api-python` 1.0.0, and the Personal API FAQ.

| Fact | Value | Source |
|---|---|---|
| Base URL | `https://personal.connectapi.garmin.com` | OpenAPI `servers` |
| Token endpoint | `POST /personalapitoken-service/personal-api/personal-api-key/token`, header `Authorization: ApiKey <key>`, body is the JWT as `text/plain`. A wrong key gives 401 with an empty body, a deleted key 404. | Garmin client `auth.py`; real API |
| Data requests | `Authorization: Bearer <JWT>` | Garmin client `client.py` |
| Token lifetime | 24 hours, or until the key expires if that is sooner; revoked when the key is deleted. No refresh tokens. Expiry read from the JWT `exp` claim without verifying the signature. | FAQ; Garmin client; real API |
| Token claims | RS256, issuer `https://diauth.garmin.com`, `garmin_guid`, `scope`, `exp`/`iat`. No key expiry, no `userProfileId`. | Real API |
| Key lifetime | 30 days, 90 days, 180 days or one year, chosen by the user. Garmin emails about a week before expiry. Shown once at creation. | FAQ |
| Endpoints | 26, all `GET`, read-only | OpenAPI |
| Security schemes in the spec | None declared | OpenAPI |
| Rate limits | Not published; no rate-limit headers in responses | FAQ; real API |
| Intended use | Individual users reading their own data; not commercial apps serving many users | FAQ |

Behaviour checked against the real API on 2026-10-23 (details under Open questions in
PLAN.md):

- A day without data, future or past, is HTTP 200 with a full summary object: `userProfileId`
  and `calendarDate` are set, every metric is null.
- Calorie totals, resting calories included, grow through the day up to the last sync.
- `timeZone` is an IANA name. `*GMT` timestamps carry no offset.
- `displayName` is a generated UUID for accounts that never set one.

### Endpoints used

| Endpoint | Used for |
|---|---|
| `GET /userprofile-service/userprofile/settings` | Display name and time zone, once per setup |
| `GET /usersummary-service/usersummary/daily?calendarDate=YYYY-MM-DD` | All current sensors, every poll; also the account ID in the config flow |
| `GET /activitylist-service/activities/search/activities?limit=1` | The owner's full name for the entry title, in the config flow only |

`GET /usersummary-service/v2/dailysummaries` returns the same data for a date range of up to a
year, with calories nested under `calories.burnedTotal` and similar. It is the candidate for
importing history into long-term statistics later. It is not used for live sensors.

## Library: aio-garmin-personal

- `GarminPersonalClient(session, api_key, *, base_url, request_timeout)`. The caller passes the
  `aiohttp.ClientSession` and owns it (rule `inject-websession`).
- `TokenProvider` keeps the JWT in memory and exchanges the key again when the token is within
  one hour of expiry (the margin Garmin's own client uses). An `asyncio.Lock` makes concurrent
  callers share one exchange. Nothing is written to disk.
- A data request answered with 401 drops the cached token and is retried once with a new
  token. A second 401 raises `GarminPersonalAuthenticationError`.
- Responses are parsed into frozen dataclasses (`DailySummary`, `UserSettings`). Each metric is
  optional and becomes `None` when missing or of the wrong type. `userProfileId` and
  `calendarDate` are required. The decoded JSON stays available as `raw`, for diagnostics.
- Typed with `py.typed`, checked with `mypy --strict` (needed for the integration's
  `strict-typing` rule).

### Error mapping

| Condition | Library exception | Integration behaviour |
|---|---|---|
| Token endpoint 401, 403 or 404 (deleted key); data endpoint 401 twice | `GarminPersonalAuthenticationError` | `ConfigEntryAuthFailed`: entities unavailable, reauth flow starts |
| HTTP 429 | `GarminPersonalRateLimitError` (`retry_after` from `Retry-After`) | `UpdateFailed(retry_after=…)`: unavailable, next poll delayed |
| Network error or timeout | `GarminPersonalConnectionError` | `UpdateFailed`: unavailable, logged once (coordinator) |
| Other non-2xx (403 on a data endpoint included), invalid JSON, missing required fields | `GarminPersonalResponseError` (`status`) | `UpdateFailed` |
| Day without data (200, metrics null) | summary with metrics `None` | sensors report `unknown` |
| 204, or 200 with an empty body (not seen from the real API) | method returns `None` | sensors report `unknown`; the config flow shows `unknown` |

During setup the coordinator's first refresh turns `UpdateFailed` into `ConfigEntryNotReady`,
so Home Assistant retries setup with backoff.

## Integration: garmin_connect_personal

### Config entry

- `data = {"api_key": …}`. No options.
- `unique_id` = Garmin `userProfileId` as a string. It appears only in daily summaries, so the
  config flow fetches today's summary (today in the Garmin time zone). Garmin returns one for
  any day, so this always identifies the account.
- Title = display name from the profile settings, unless it is missing or a UUID; then the
  `ownerFullName` of the most recent activity; then "Garmin Connect" (ADR-0022). The device is
  named after the title, and entity IDs after the device.
- Flows: `user` (paste key), `reauth_confirm` (after Garmin rejects the key), `reconfigure`
  (replace a working key before it expires). Reauth and reconfigure abort with `wrong_account`
  when the new key belongs to a different `userProfileId`.

### Coordinator

- One `DataUpdateCoordinator`, polling every 10 minutes (rule `appropriate-polling`; Garmin
  publishes no limits, and watch syncs are minutes apart).
- `_async_setup` reads the profile time zone once. `gmt` maps to UTC. An unknown zone name
  falls back to the Home Assistant time zone, with a warning.
- Each poll requests the calendar day that is current in the Garmin time zone. Garmin assigns
  data to days in that zone; using Home Assistant's zone would request the wrong day for a user
  travelling or with a mismatched Home Assistant setting.
- Until the day before is final, each poll also requests it: from 15 minutes after midnight
  (time for the recorder to compile the day's last hour) until the first poll whose summary
  for today has a `lastSyncTimestampGMT`. That field is null until the first sync of the new
  day, and that sync uploads what the watch recorded late the day before. ADR-0023.
- Data held: `GarminConnectPersonalData(summary: DailySummary | None, previous_day:
  DailySummary | None)`; `previous_day` is set only while the day before may still change.

### Device and entities

One device per config entry, `DeviceEntryType.SERVICE`, identifier `(domain, userProfileId)`,
named after the entry title. Entities use `has_entity_name` and translated names; unique IDs are
`<userProfileId>_<key>`.

| Key | Source field | Unit | Device class | State class | Default |
|---|---|---|---|---|---|
| `total_calories` | `totalKilocalories` | kcal | energy | total | enabled |
| `active_calories` | `activeKilocalories` | kcal | energy | total | enabled |
| `resting_calories` | `bmrKilocalories` | kcal | energy | total | disabled |
| `steps` | `totalSteps` | steps | – | total | enabled |
| `distance` | `totalDistanceMeters` | m (shown in km) | distance | total | enabled |
| `floors_ascended` | `floorsAscended` | floors | – | total | disabled |
| `intensity_minutes` | `moderateIntensityMinutes + 2 × vigorousIntensityMinutes` | min | – | total | enabled |
| `resting_heart_rate` | `restingHeartRate` | bpm | – | measurement | enabled |
| `average_stress` | `averageStressLevel` | – | – | measurement | disabled |
| `body_battery` | `bodyBatteryMostRecentValue` | – | – | measurement | enabled |
| `last_sync` | `lastSyncTimestampGMT` | – | timestamp | – | enabled, diagnostic |

Daily totals use state class `total` with `last_reset` set to midnight of the summary's
calendar day in the Garmin time zone. Long-term statistics start a new cycle whenever
`last_reset` changes, so each day sums from zero however the first value of the day compares
with the last value of the day before. See DECISIONS.md ADR-0010 for why not `total_increasing`.

Intensity minutes use Garmin's weighting, where a vigorous minute counts as two.

### Correcting the day before

A daily total's state only ever shows the current day, so whatever syncs after midnight for
the day before never reaches the state, and that day's long-term statistics stop at the last
value before midnight. When the coordinator has the day before, each daily-total sensor reads
the day's `change` from the recorder (Garmin's midnight to midnight) and, if it differs from
Garmin's total for the day, calls the recorder's `async_adjust_statistics` with the difference
from the day's last hour on. That shifts the running `sum` of every later row by the same
amount, so the day before gets the full total and later days keep their own change. Reading
the recorded change, not a value kept in memory, makes the correction safe to repeat after a
restart. ADR-0023.

Known effects:

- Calorie totals can grow by a lot: resting calories reach the full day only with the first
  sync after midnight.
- On the day a sensor is created, the recorder takes its first value as the starting point,
  so the correction adds that day's data from before the sensor existed.
- Only the day before is corrected. A watch that does not sync for longer leaves the earlier
  days short.

### Diagnostics

The API key, `userProfileId`, `displayName`, `userDailySummaryId` and `uuid` are redacted, and
so is `bodyBatteryActivityEventList` as a whole: its entries carry the watch's `deviceId`, the
activity IDs and names, and the times of sleep and exercise, and no sensor reads it. The raw
daily summary is included otherwise, because it is what is needed to debug a wrong value.

### Translations

`strings.json` is the source, written as core expects, with `[%key:…%]` references.
`translations/en.json` is generated from it by `script/gen_translations.py`, because a custom
integration is loaded without core's build step that resolves references. CI fails when the
generated file is stale.

## Testing

| Repository | Approach |
|---|---|
| Library | `pytest` against a local `aiohttp` test server that answers queued replies and records requests. Real HTTP, so headers, query strings, timeouts and connection errors are exercised. 95% coverage gate. |
| Integration | `pytest-homeassistant-custom-component` (the core test harness packaged for custom integrations). The library client is patched with an autospec mock; fixtures are `DailySummary`/`UserSettings` built from JSON, so parsing is shared with the library. 95% coverage gate (rule `test-coverage`). |

Expected values in tests are literals from the fixtures, never recomputed with the code under
test.
