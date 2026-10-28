# Decisions

One entry per decision. Add new ones at the end with the next number. When a decision is
reversed, mark it `Superseded by ADR-NNNN` instead of deleting it.

## ADR-0001: Write our own async library instead of using Garmin's client

**Status:** accepted, 2026-10-22

Garmin published `garmin-connect-personal-api-python` 1.0.0 on PyPI on 2026-10-21 (Apache-2.0,
sdist and wheel, tag `v1.0.0`). It cannot be the integration's dependency:

- GitHub issues are disabled on `garmin/connect-personal-api-python`. The core checklist requires
  an enabled issue tracker.
- The repository has no CI workflows, so the PyPI release was not built in public CI. That fails
  the Bronze rule `dependency-transparency`.
- It is synchronous (`requests`), which fails the Platinum rules `async-dependency` and
  `inject-websession`.
- Its token cache is a file under `~/.config/garmin`, which does not fit Home Assistant.

So `aio-garmin-personal` is written from scratch with `aiohttp`. Garmin's client is the reference
for the token endpoint and header formats, which the OpenAPI document does not describe.

## ADR-0002: Two repositories in one workspace directory

**Status:** accepted, 2026-10-22

Both repositories are checked out side by side in one workspace directory, which is not a git
repository. It holds:

- `aio-garmin-personal/`: the library repository, published to PyPI from its own tags.
- `ha-garmin-connect-personal/`: the integration repository, released to HACS from its own tags.
- `reference/`: material that must not be published (ADR-0014).
- `CLAUDE.md`: orientation for Claude Code sessions started in the workspace, including how
  the maintainer handles the Personal API key locally.

One repository cannot serve both: PyPI versions must match tags in the library's public
repository (`dependency-transparency`), and HACS reads versions from the integration
repository's releases. The project documents (design, plan, decisions) live in the integration
repository's `docs/`, because the integration is the product and they are versioned there. The
workspace `CLAUDE.md` is not versioned, so it only points to them.

## ADR-0003: Names

**Status:** accepted, 2026-10-22

| Thing | Name |
|---|---|
| PyPI distribution | `aio-garmin-personal` |
| Python package | `aio_garmin_personal` |
| Library repository | `github.com/pentiak/aio-garmin-personal` |
| Integration domain | `garmin_connect_personal` |
| Integration repository | `github.com/pentiak/ha-garmin-connect-personal` |
| Display name | Garmin Connect Personal |

`garmin_connect` is taken: it is the domain of the cyberjunky HACS integration and of the
former core integration. Two integrations with the same domain cannot be installed together.
The PyPI name was free on 2026-10-22.

## ADR-0004: Develop as a custom integration laid out the way core expects

**Status:** accepted, 2026-10-22

The integration is built and released through HACS first, but written to core's rules from the
start, so the core submission is a copy rather than a rewrite:

- `quality_scale.yaml` is kept current; it is the per-rule checklist.
- `strings.json` uses core's `[%key:…%]` references; `translations/en.json` is generated
  (DESIGN.md, Translations).
- Code style follows core: `ruff` with core's isort settings, `typing.override`, `probatio`
  schemas, `ConfigEntry.runtime_data`, `strict` mypy on the integration code.
- Things only a custom integration needs (`version` in `manifest.json`, `hacs.json`, the
  translations generator, a `brand/` folder) are removed at submission.

## ADR-0005: Poll the single-day summary every 10 minutes

**Status:** accepted, 2026-10-22

All current sensors come from `GET /usersummary-service/usersummary/daily`, one request per
poll, one coordinator. After midnight a second request per poll fetches the day before until
it is final (ADR-0023). Garmin publishes no rate limits. Ten minutes keeps the daily request
count at 144 and is short compared with how often watches sync. The interval is a constant,
not an option, following core practice; check core's current policy before adding an option.

## ADR-0006: The day boundary comes from the Garmin profile time zone

**Status:** accepted, 2026-10-22

Garmin assigns wellness data to calendar days in the time zone of the user profile
(`timeZone` in the profile settings). The coordinator reads that zone once at setup and
requests "today" in it. `gmt` is mapped to UTC. An unknown zone name falls back to the Home
Assistant zone with a warning.

The zone is not refreshed until the entry reloads. If Garmin changes it while travelling, the
first polls after midnight may request the wrong day. Revisit once real behaviour is known
(PLAN.md, open questions).

## ADR-0007: The account is identified by `userProfileId`

**Status:** accepted, 2026-10-22; revised 2026-10-23

The config entry's `unique_id`, the device identifier and the entity unique IDs use the
Garmin `userProfileId`. It appears only in daily summaries. The profile settings have a display
name, which users can change and which is a generated UUID for accounts that never set one.

The config flow fetches today's summary (today in the Garmin time zone). The real API returns a
summary with `userProfileId` for any day, even one without data, so the original fallback to
yesterday and the `no_data` error were removed on 2026-10-23.

The token's `garmin_guid` claim is another stable identifier. It is not used: switching would
change every unique ID, and reading it would make the integration depend on the token's
contents, which Garmin does not document.

## ADR-0008: Token handling

**Status:** accepted, 2026-10-22

- The JWT is held in memory only, per client instance. It is not stored in the config entry, so
  each Home Assistant restart costs one token exchange.
- It is renewed when it is within one hour of its `exp`, the margin Garmin's client uses.
- A 401 on a data endpoint invalidates the token and retries once; a second 401 is an
  authentication failure.
- A 403 on a data endpoint is a `GarminPersonalResponseError`, not an authentication failure.
  A valid token that is refused a resource does not mean the key is bad, and starting a reauth
  flow for it would ask the user for a key they already have.

## ADR-0009: Key expiry is handled by reauthentication only

**Status:** accepted, 2026-10-23

Keys expire after the period the user chose, between 30 days and one year. When one expires,
Garmin rejects it, the integration raises `ConfigEntryAuthFailed`, and Home Assistant asks the
user to re-authenticate with a new key. Nothing warns earlier inside Home Assistant:

- No endpoint, header or token claim reports the key's expiry date (checked against the real
  API on 2026-10-23). A token shorter than 24 hours shows the key expires within a day, which is
  too late to be useful.
- Garmin emails the user about a week before a key expires, and the reconfigure flow lets the
  user replace a key that still works.

The alternative, an optional expiry date typed in during setup with a repair issue seven days
ahead, was rejected: it adds a field to the setup form and depends on a date the user can
mistype. `repair-issues` is exempt in `quality_scale.yaml` for this reason.

## ADR-0010: Sensor modelling

**Status:** accepted, 2026-10-22

- Daily totals (calories, steps, distance, floors, intensity minutes) use state class `total`
  with `last_reset` = midnight of the summary's `calendarDate` in the Garmin time zone.
  `total_increasing` was the first choice, as in core's `google_health`, but the recorder only
  detects a reset of a `total_increasing` sensor when the value drops below 90% of the previous
  one (`reset_detected` in `homeassistant/components/sensor/recorder.py`). Calorie totals do not
  start from zero: if Garmin reports the full day's BMR from the first sync (open question 1),
  `resting_calories` stays near the same value across midnight, and `total_calories` after a rest
  day can start above 90% of the day before. Neither reset would be recorded, and the day's sum
  would be wrong. With `last_reset` the cycle boundary is explicit, and a total that decreases
  within a day (open question 8) reduces the sum instead of starting a new cycle.
- Calories use device class `energy` with `kcal`.
- Body Battery has no unit. It is Garmin's 0–100 score, not a percentage of anything, and the
  `battery` device class would mark it as a device battery.
- Intensity minutes are `moderate + 2 × vigorous`, Garmin's own weighting.
- Resting calories, floors and average stress are disabled by default; most users do not need
  them.
- A missing summary makes every sensor `unknown`, not `0`. "No data yet" and "zero steps" are
  different facts.

## ADR-0011: Library tests use a local aiohttp server

**Status:** accepted, 2026-10-22

`aioresponses` 0.7.9 fails with aiohttp 3.14 (`ClientResponse.__init__() missing 1 required
keyword-only argument: 'stream_writer'`). The library tests run against a real
`aiohttp.test_utils.TestServer` with queued replies instead (`tests/conftest.py`, `FakeGarmin`).
This also exercises real headers, query strings and timeouts.

## ADR-0012: Local Python and CI versions

**Status:** accepted, 2026-10-22

The only Python on the development machine is Homebrew's 3.15. Home Assistant 2026.10.2 requires
`>=3.14.2` and ships on 3.14. `pytest-homeassistant-custom-component` 0.13.373 (which pins
`homeassistant==2026.10.2`) installs and passes on 3.15, so local work uses a project venv on
3.15 (`python3 -m venv .venv`). CI runs the library on 3.13 and 3.14 and the integration on
3.14, the version users run. A failure that appears only locally may be a 3.15 difference;
check CI before chasing it.

## ADR-0013: Minimum Home Assistant version 2026.10.0

**Status:** accepted, 2026-10-22

Core config flows use `probatio` schemas, and HA 2026.10's `FlowHandler` types expect them;
voluptuous schemas fail strict mypy. The integration targets the release it is tested against,
set in `hacs.json`. Raise it when the test harness pin moves; do not support older releases.

## ADR-0014: Garmin's OpenAPI document stays out of the repositories

**Status:** accepted, 2026-10-22

Garmin does not publish the spec as a file; it is embedded in the Swagger page's JavaScript
bundle. The extracted copy is in the workspace at
`reference/garmin-personal-api-openapi-1.0.0.json`, which is not in either repository, because
it is Garmin's documentation and the repositories will be public. The library repository
carries `scripts/extract_openapi.py` to regenerate it.

## ADR-0015: Apache-2.0 for both repositories

**Status:** accepted, 2026-10-22

Home Assistant core is Apache-2.0, and core requires dependencies under OSI-approved licences
compatible with it.

## ADR-0016: Per-repository git identity

**Status:** accepted, 2026-10-22

Commits in both repositories use `Oskar Majchrzak <pentiak@gmail.com>`, set with
`git config --local` so that the global identity on the development machine does not apply.
Check with `git config --local user.email` before the first commit in a fresh clone.

## ADR-0017: Entry title from the display name, unless it is a UUID

**Status:** accepted, 2026-10-23; amended by ADR-0022

Garmin fills `displayName` with a generated UUID for accounts that never set a display name.
Using it as the title would put the UUID into the device name and every entity ID. The title is
the display name when it is set and does not parse as a UUID, and "Garmin Connect" otherwise.
Users can rename the entry and the device in Home Assistant.

## ADR-0018: Lint with Home Assistant core's ruff configuration

**Status:** accepted, 2026-10-23

`pyproject.toml` and `tests/ruff.toml` carry core's ruff configuration, copied from the core
`dev` branch, extending ADR-0004. Only `extend-exclude` and the per-file ignores for core's own
paths were dropped, and `custom_components` was added as first party. Consequences:

- Line length is the formatter default, 88.
- `from __future__ import annotations` is banned. Python 3.14, the minimum for the
  integration, evaluates annotations lazily, so it is not needed.
- Every function, tests included, needs a docstring.

The library is not part of core and targets Python 3.13, which evaluates annotations eagerly,
so it keeps `from __future__ import annotations`. It uses core's rule list plus the complete
bandit (`S`), datetime (`DTZ`), builtins (`A`), naming (`N`), comprehension (`C4`) and
commented-out code (`ERA`) families, with test-only ignores for `assert` and private access.

## ADR-0019: Actions are pinned to commit SHAs, with a seven-day cooldown

**Status:** accepted, 2026-10-23

Every action in both repositories is referenced by a full commit SHA, with its version in a
comment. In March 2026 an attacker replaced 76 of the 77 version tags of
`aquasecurity/trivy-action` with commits that stole CI secrets; workflows pinned to a SHA ran
the code they had reviewed.

New releases are adopted after seven days: when pinning, the newest release at least a week
old is chosen, and Dependabot (`.github/dependabot.yml`, weekly) uses `cooldown: 7` days. A
compromised release is usually found and withdrawn within that time.

Two references stay on a branch: `home-assistant/actions/hassfest@master` and
`hacs/action@main`. Neither project publishes releases of them; hassfest on `master` follows
core's current rules, which is the point of running it, and a pinned commit would validate
against outdated rules. Both come from the projects whose code the integration runs inside.
`.github/zizmor.yml` allows exactly these two.

## ADR-0020: Security scans

**Status:** accepted, 2026-10-23

| Check | Where | Covers |
|---|---|---|
| gitleaks | `security.yml`, full history | secrets committed to git |
| detect-secrets | pre-commit hook | secrets before they are committed; `.secrets.baseline` lists known fakes |
| Trivy `fs` | `security.yml` | vulnerable pinned dependencies, secrets, misconfiguration |
| pip-audit | library `ci.yml` | vulnerabilities in the library's installed runtime dependencies |
| zizmor | `security.yml`, pre-commit | insecure GitHub Actions workflows |
| CodeQL | `security.yml`, public repositories only | Python and workflow code analysis |
| Dependabot | `.github/dependabot.yml` | outdated actions and Python packages |

Trivy finds Python dependencies only in pinned files such as `requirements_test.txt`; the
library declares `aiohttp>=3.11` with no lock file, so pip-audit audits what is actually
installed instead. The integration has no pip-audit job: its only runtime dependency is the
library, audited in its own repository, and the rest of its environment is Home Assistant's.

Code scanning, GitHub secret scanning, push protection and branch rulesets are free only for
public repositories. The CodeQL job is skipped while a repository is private and starts on its
own once it is public; the rest are switched on in phase 2 (PLAN.md).

Local hooks run tools from the project venv only, so nothing is installed outside it.

## ADR-0021: What the public repositories may contain

**Status:** accepted, 2026-10-23

Both repositories are public, and so is their history. They contain the code, the project
documents and test data, and nothing about the maintainer beyond the name and address in the
commits and the package metadata:

- **No real account data.** Test fixtures keep the field names, types and null patterns of
  real responses, but every identifier, metric and timestamp is made up. A real response can
  identify a person (IDs, display name) and is health data even without identifiers (heart
  rate, SpO2, sleep times). Before adding a fixture from a real response, replace all of it.
- **No personal setup.** How the maintainer stores the API key, local paths and machine details
  belong in the workspace `CLAUDE.md`, which is not versioned.
- **Findings, not measurements.** Observations about the API are written as general
  statements ("resting calories grow through the day"), not as the maintainer's numbers.

## ADR-0022: The full name from the activities titles an entry without a display name

**Status:** accepted, 2026-10-27

Accounts often never set a display name, so under ADR-0017 every such entry was titled "Garmin
Connect". Two accounts in one Home Assistant could only be told apart by renaming them. The
profile settings have no other name field. Garmin returns the account holder's full name only
as `ownerFullName` on activities, so the config flow reads the most recent activity
(`limit=1`).

Checked against the real API on 2026-10-27: `ownerFullName` is set on activities of an account
whose display name is a UUID, and holds the name as entered in the profile, which may be a
first name only. `limit` is honoured, and `startTimeGMT` has the form `2026-10-27 15:20:09`.
Activities also carry start and end coordinates, so their raw data must not reach diagnostics.

The title is the first of:

1. the display name, when it is set and is not a UUID: the user chose it;
2. the full name from the most recent activity;
3. "Garmin Connect".

An account without activities, an activity without a name, or an activity list that cannot be
read leads to the next step, never to a failed flow. The title is set when the entry is
created; existing entries keep theirs. The full name ends up in the device name and the entity
IDs, as a display name does.

## ADR-0023: Correct the day before in the sensors' own statistics

**Status:** accepted, 2026-10-27

Running against a real account showed that a day's long-term statistics end at the last sync
before midnight. Steps, distance and calories recorded later that evening reach Garmin with the
first sync after midnight, when the sensors already show the new day, so Home Assistant never
records them.

After midnight the coordinator also fetches the day before, until today's summary has a last
sync time (DESIGN.md, Coordinator). Each daily-total sensor then compares Garmin's total with
the change the recorder holds for that day, and adds the difference to its own statistic with
`Recorder.async_adjust_statistics`, from the day's last hour on. The same operation backs
"Adjust a statistic" in the developer tools: it adds the amount to the `sum` of every row from
that hour on, so later days keep their own change and no spike appears.

Alternatives:

- **External statistics** (`garmin_connect_personal:…`, as opower and ista_ecotrend do) would
  hold correct daily totals, but next to the sensor's statistic, which would stay short. The
  user would see two step counts per day that disagree. External statistics remain the way to
  import history from before the entry existed (PLAN.md, phase 5).
- **Keeping yesterday's state until the first sync** would put the late data into the
  statistics, but in the hour of the sync, so on the wrong day.

No core integration calls `async_adjust_statistics` today; only the recorder's WebSocket API
does. Expect to explain this in the core review, and fall back to external statistics if
reviewers reject it.

## ADR-0024: Releases are tagged by hand and published by a workflow

**Status:** accepted, 2026-10-27

Both repositories release the same way. A release PR sets the version (`version` in the
library's `pyproject.toml`, in the integration's `manifest.json`) and moves the changelog
entries under a `## X.Y.Z - YYYY-MM-DD` heading. After it merges, the maintainer tags that
commit on `master` as `vX.Y.Z`. The tag starts `release.yml`, which checks that the tag matches
the version and creates the GitHub release with that changelog section as its notes; the
library's workflow also publishes to PyPI first. A missing section fails the workflow before
anything is published. HACS installs the integration from these GitHub releases.

`gh`, preinstalled on the runners, creates the release, so no further action has to be pinned
(ADR-0019).

release-please was considered and not adopted:

- It derives versions and changelogs from Conventional Commits. Neither repository uses them,
  and with squash merges every PR title would have to follow them.
- A tag it creates with the workflow token does not start other workflows, so the library's
  PyPI publishing on tag push would need a personal access token, a GitHub App, or to move into
  the release-please workflow.
- It adds an action with write permissions to two repositories that release rarely, to save
  one small commit and one tag per release.

Revisit if releases become frequent or other contributors join.

## ADR-0025: The library covers the whole Personal API, typed from probed responses

**Status:** accepted, 2026-10-28

aio-garmin-personal is useful without Home Assistant, so it covers every endpoint in Garmin's
OpenAPI document, not only those the integration uses. The integration keeps adding sensors
one at a time (phase 5); the library does not wait for it.

- **Typed fields plus `raw`.** Each response becomes a frozen dataclass with the fields a
  caller is likely to use, and the decoded JSON in `raw`. The document lists about 1,600
  fields in 109 schemas; typing all of them would be large and partly wrong, because the real
  responses already differ from the schemas (fields missing, epoch milliseconds where the
  document says ISO strings). Anything not typed is still in `raw`.
- **Probe first.** Before a model is written, a script run with the maintainer's key records
  each endpoint's field names, JSON types, null patterns and range limits, never values. The
  findings go into DESIGN.md as general statements (ADR-0021); fixtures are made up in the
  recorded shape.
- **Unverified endpoints are marked.** Where the maintainer's account has no data (hydration,
  nutrition, the menstrual cycle), the model is typed from the document and its docstring
  says so, until a real response confirms it.
- **One convention for names.** Per-day models are named `Daily…`; instants end in
  `_time_gmt` and are timezone-aware UTC; quantities carry their unit in the name
  (`_seconds`, `_meters`, `_ml`) and keep Garmin's unit.
- **Argument checks stay small.** A range with `start` after `end` raises `ValueError`
  without a request. The longest range per endpoint is documented, not enforced, because it
  is Garmin's and may change; a longer range raises `GarminPersonalResponseError` with 400.
- **Left out:** `/weight-service/weight/all/{startDate}/{endDate}`, which answered HTTP 400 to
  every request tried, including single days that have a weight entry.
  `/weight-service/weight/range/{startDate}/{endDate}` returns the same entries.

The endpoints arrive in batches, one PR each, released together as 0.3.0.
