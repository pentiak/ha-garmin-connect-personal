# Plan

## Status

Update this section at the end of every working session.

- **Last updated:** 2026-10-27
- **Current phase:** 3 (integration in a real Home Assistant, first HACS release)
- **State:** Phases 0 to 2 are done, with guardrails (ADR-0018 to ADR-0020). Both GitHub
  repositories were recreated on 2026-10-23 with a single fresh commit each; ADR-0021
  records what they may contain. Both are public, and their settings match Repository
  settings below. aio-garmin-personal 0.2.0 is on PyPI, published by `release.yml` through
  trusted publishing. Both repositories release from a tag (ADR-0024).
- **Phase 3 step 3 in progress:** the first version ran from 2026-10-23 on a real instance
  with two accounts. Daily totals reset at Garmin's midnight, including the DST change on
  2026-10-25, and no update failed. Its three findings are fixed on `master`: diagnostics
  redact the activity event list, an entry without a display name is titled with the
  account holder's name (ADR-0022), and data synced after midnight is added to the day
  before (ADR-0023). The instance does not run that code yet.
- **Next step:** install `master` on the instance (HACS → redownload, or copy
  `custom_components/garmin_connect_personal`), run it for a few nights, and compare the
  daily statistics with the Garmin Connect app; test reauth and reconfigure; then the release
  PR for `v0.1.0`, which dates the `CHANGELOG.md` entry.

## Phases

The quality-scale state of each rule is tracked in
`custom_components/garmin_connect_personal/quality_scale.yaml`, not here.

### Phase 0: Scaffold (done 2026-10-22)

- Library with token exchange, `async_get_user_settings`, `async_get_daily_summary`, typed
  exceptions, tests, CI and release workflows.
- Integration with user, reauth and reconfigure flows, coordinator, 11 sensors (daily totals
  as `total` with `last_reset`), diagnostics,
  translations, icons, `quality_scale.yaml`, tests, hassfest and HACS validation workflows.
- DESIGN.md, DECISIONS.md, this plan, CLAUDE.md files.

### Phase 1: Verify against the real API (done 2026-10-23)

Needs a Personal API key (Garmin Connect → Settings → Personal API Key). Keep the key out of
both repositories. A script that needs it reads it from `GARMIN_PERSONAL_API_KEY` and never
prints the key or the token; how the maintainer stores and passes the key is in the workspace
notes, which are not published.

1. Done 2026-10-23: a scratch script (not kept) called the token endpoint with a wrong and the
   real key, the profile settings, the daily summary for today, yesterday, tomorrow and
   2001-01-01, and the date-range summary. Re-create it from this description if the API needs
   probing again; it must read the key from `GARMIN_PERSONAL_API_KEY` and never print the key
   or the token.
2. Done: answers are under Open questions and in DESIGN.md.
3. Done: fixtures in both repositories have the shape of the real responses, with every
   identifier, metric and timestamp replaced by made-up values (ADR-0021).
4. Done: ADR-0009 decided, reauthentication only; `repair-issues` is exempt.

**Done when:** every open question has an answer or is explicitly deferred, and the fixtures
match the real response shapes.

### Phase 2: Publish the library (done 2026-10-23)

1. Done: `github.com/pentiak/aio-garmin-personal` is public, with issues on, as
   `dependency-transparency` requires.
2. Done: on PyPI, a trusted publisher: project `aio-garmin-personal`, owner `pentiak`,
   repository `aio-garmin-personal`, workflow `release.yml`, environment `pypi`. In the GitHub
   repository, the `pypi` environment, limited to `v*.*.*` tags.
3. Done: move the CHANGELOG `Unreleased` section to `0.1.0`, commit, tag `v0.1.0`, push the tag.
   The `release` workflow checks that the tag matches `pyproject.toml`, builds, publishes and
   creates the GitHub release.
4. Done: add `tests` to the integration's required checks (see Repository settings).

#### Repository settings

Both repositories, applied with `gh` after they were recreated:

- Public, issues on, private vulnerability reporting on.
- Secret scanning, push protection and Dependabot security updates on.
- Integration only: description "Home Assistant integration for the Garmin Connect Personal
  API" and topics `home-assistant`, `hacs`, `hacs-integration`, `garmin`, `garmin-connect`
  (the HACS check needs both).
- Ruleset "Protect master" on the default branch: no deletion, no force pushes, changes through
  a pull request with resolved review threads (no approvals, as there is one maintainer), and
  required checks from GitHub Actions (app id 15368). Rulesets need a public repository on the
  free plan.
  - Library checks: `test (3.13)`, `test (3.14)`, `dependency-audit`, `gitleaks`, `trivy`,
    `zizmor`, `codeql`.
  - Integration checks: `tests`, `hassfest`, `hacs`, `gitleaks`, `trivy`, `zizmor`, `codeql`.
    `tests` installs the pinned library version from PyPI, so a library bump must be released
    before the integration PR that raises the pin can pass.

**Done when:** `pip install aio-garmin-personal==0.1.0` works and the PyPI release links to
the tag. Then set `dependency-transparency: done` in `quality_scale.yaml`.

### Phase 3: Integration on GitHub, in a real Home Assistant, first HACS release

1. Done: `github.com/pentiak/ha-garmin-connect-personal` is public. The `tests` workflow
   installs the library from PyPI.
2. Done: `validate` (hassfest, HACS action) is green.
3. Run it in a real Home Assistant: add the repository as a HACS custom repository, or copy
   `custom_components/garmin_connect_personal` into a test instance's config. Run it for at
   least several days across midnight and check:
   - daily totals start a new statistics cycle at Garmin midnight (`last_reset`), and the
     long-term statistics for a day match the Garmin Connect app;
   - an expired or deleted key leads to the reauth notification, and a new key fixes it;
   - reconfigure works with a new key for the same account.
4. Release `v0.1.0` of the integration: a release PR dates the `CHANGELOG.md` entry, then
   tag the merge commit `v0.1.0`; `release.yml` creates the GitHub release (ADR-0024). HACS
   installs from releases.

**Done when:** installed through HACS on a real instance and stable for a week.

### Phase 4: Documentation and brand (Bronze to Gold)

1. Write the user documentation in the integration README, covering every `docs-*` rule in
   `quality_scale.yaml`: description, installation (HACS and manual), setup parameters, removal,
   data update interval, known limitations, troubleshooting, use cases, automation examples,
   supported functions. Core needs the same content as a PR to `home-assistant.io` later.
2. Check Garmin's brand guidelines for using the name and logo. Until then
   `custom_components/garmin_connect_personal/brand/` holds a generic watch icon (`icon.png`,
   `icon@2x.png`) drawn by `script/draw_placeholder_icon.py`, which satisfies the HACS brands
   check. If Garmin allows its logo, replace the icon and add `logo.png` and the `dark_`
   variants as needed. Core instead needs a PR to `home-assistant/brands`.

**Done when:** every rule in `quality_scale.yaml` is `done` or `exempt`.

### Phase 5: More data

Each item needs a library method, tests, and a library release before the integration can use
it. Candidates, from the endpoints in the OpenAPI document:

- Sleep: `/sleep-service/sleep/dailySleep` (score, duration, stages).
- HRV: `/hrv-service/hrv/{calendarDate}` (last night average, status).
- Body Battery details, SpO2, respiration: some are already in the daily summary.
- Weight: `/weight-service/weight/range/{startDate}/{endDate}`.
- Last activity: `/activitylist-service/activities/search/activities`.
- History import into long-term statistics from `/usersummary-service/v2/dailysummaries`,
  as external statistics; the sensors' own statistics only cover the day before (ADR-0023).

A second coordinator with a longer interval suits data that changes once a day (sleep, HRV).

### Phase 6: Submit to Home Assistant core

1. Fork `home-assistant/core`, open the dev container, and run
   `python3 -m script.scaffold integration` with the same domain to get current boilerplate.
2. Copy the integration in. Remove `version` from `manifest.json`; add
   `"quality_scale": "platinum"` only if every rule is met. Delete `translations/`; core
   generates it. Opt the integration into core's strict type checking (check how core
   currently lists strictly typed integrations).
3. Run `python3 -m script.hassfest`, `python3 -m script.gen_requirements_all`, the tests and
   mypy as core runs them.
4. Open the first PR with the `sensor` platform only. Reviewers usually ask for a small first
   PR; add more in follow-ups. Open the documentation PR to `home-assistant.io` and the brand PR
   to `home-assistant/brands` alongside.
5. After merge, keep the HACS repository for users on older Home Assistant releases until they
   have moved, or archive it with a note pointing to core.

## Open questions

Answered 2026-10-23 from the real API unless marked open.

1. **Does `bmrKilocalories` grow through the day?** Yes. In a morning summary it equalled the
   previous day's total scaled by the share of the day up to the last sync. All calorie totals
   mean "so far".
2. **What does a day without data return?** HTTP 200 with a full object: `userProfileId`,
   `calendarDate`, `displayName`, `source`, the `includes*` flags (false), every metric null.
   The same for a future date and for 2001-01-01. Never 204 or an empty body.
3. **What does the token endpoint return for a bad key?** A wrong key gives 401 with an empty
   body and `WWW-Authenticate: Bearer`. A deleted key gives 404 (checked 2026-10-27), and the
   tokens already issued for it are rejected with 401 from the next request on. *Open:* an
   expired key, testable only when one expires.
4. **Which claims does the JWT carry?** RS256; `iss` `https://diauth.garmin.com`; `exp − iat`
   = 86 400 s; `garmin_guid`, `client_id`, `jti`, `scope` (`CONNECT_READ` and
   `PERSONAL_API_{FITNESS,NUTRITION,USER,WELLNESS}_READ`). No key expiry and no
   `userProfileId`.
5. **Rate limits?** *Open.* No rate-limit headers on any response; Cloudflare is in front.
6. **Formats?** `timeZone` is an IANA name such as `Europe/Berlin`. `*GMT` timestamps have no
   offset and variable fractions, for example `2026-10-23T06:12:48.317` and
   `2026-10-23T06:09:00.0`.
7. *Open (phase 4):* Garmin's terms and brand guidelines: may an open-source integration use
   the Garmin name in its title and the logo in its brand images?
8. *Open:* can a total decrease within a day, for example when an activity is deleted? With
   `total` and `last_reset` that reduces the day's sum, which is correct; confirm it happens.

Also observed:

- `displayName` in the profile settings is a UUID for an account that never set one. It is
  missing from a summary that has data and present in an empty one.
- `lastSyncTimestampGMT` is null for past days; only today's summary has it.
- The real summary had no field outside the OpenAPI schema. Eight schema fields were absent:
  `dailyPushesGoal`, `displayName`, `hydrationGoalInML`, `hydrationValueInML`, `isJetLagDay`,
  `jetLagTripName`, `totalPushDistance`, `totalPushes`.
- `/v2/dailysummaries` returns the same calorie values as integers under
  `calories.burnedResting`, `burnedActive`, `burnedTotal`.
