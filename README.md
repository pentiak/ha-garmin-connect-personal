# Garmin Connect Personal for Home Assistant

The **Garmin Connect Personal** integration connects Home Assistant to your
[Garmin Connect](https://connect.garmin.com/) account through Garmin's official
[Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api). Garmin
Connect is where Garmin watches and fitness trackers store what they record: steps, calories,
heart rate, stress, Body Battery and more. The integration reads your daily totals from it.

It uses a Personal API key that you create in Garmin Connect. It does not use your Garmin
password and does not need multi-factor authentication codes.

This is not a Garmin product.

## Use cases

Your watch records your activity all day and syncs it to Garmin Connect through the phone app.
With the integration, those numbers are in Home Assistant:

- See today's steps, calories and intensity minutes on a dashboard next to the rest of your
  home.
- Get a reminder in the evening when you have not reached your step goal.
- Dim the lights or start a wind-down scene when your Body Battery is low.
- Keep a long-term history of your daily totals in Home Assistant's statistics, for example to
  compare weeks or months in a statistics graph card.

## Prerequisites

1. A Garmin Connect account with a device that syncs to it.
2. A Personal API key. In Garmin Connect, open **Settings → Personal API Key** and create one.
   Choose how long it stays valid: 30 days, 90 days, 180 days or one year. Garmin shows the key
   only once, so copy it before you close the page.
3. Home Assistant 2026.10 or later.

## Installation

### HACS

1. In HACS, add `https://github.com/pentiak/ha-garmin-connect-personal` as a custom repository
   of type Integration.
2. Install **Garmin Connect Personal** and restart Home Assistant.

### Manual

Copy `custom_components/garmin_connect_personal` into the `custom_components` folder of your
Home Assistant configuration and restart Home Assistant.

## Setup

1. Go to **Settings → Devices & services** and select **Add integration**.
2. Search for **Garmin Connect Personal** and select it.
3. Fill in the form:

   | Field | Description |
   |---|---|
   | **API key** | The Personal API key of your Garmin Connect account, from step 2 of the prerequisites. |

The entry is named after your Garmin display name. To add another person's account, add the
integration again with a key from their account.

### Replacing the key

Before a key expires, Garmin sends you an email. Create a new key in Garmin Connect, then open
the integration entry in **Settings → Devices & services**, select **Reconfigure** from its menu,
and paste the new key. The new key must belong to the same Garmin account.

## Supported functionality

Each Garmin account becomes one device with the sensors below. All values are for the current
day in the time zone set in your Garmin profile, and start again from zero at midnight in that
zone.

| Sensor | Unit | Description |
|---|---|---|
| Total calories | kcal | Calories burned today, resting and active together. |
| Active calories | kcal | Calories burned through activity today. |
| Resting calories | kcal | Calories burned at rest today (basal metabolic rate). Disabled by default. |
| Steps | steps | Steps taken today. |
| Distance | km | Distance covered today. |
| Floors climbed | floors | Floors climbed today. Disabled by default. |
| Intensity minutes | min | Today's intensity minutes, where Garmin counts a vigorous minute as two. |
| Resting heart rate | bpm | Today's resting heart rate. |
| Average stress | | Today's average stress level, from 0 to 100. Disabled by default. |
| Body Battery | | The most recent Body Battery value, from 0 to 100. |
| Last sync | | When the device last synced to Garmin Connect. Diagnostic. |

The daily totals (calories, steps, distance, floors and intensity minutes) are recorded in
long-term statistics as one value per day. To enable a sensor that is disabled by default, open
it in **Settings → Devices & services → Entities** and turn on **Enabled**.

## Data updates

The integration polls Garmin every 10 minutes. Garmin only has new data after your device has
synced to Garmin Connect, which the phone app does every so often in the background, so values
can be behind by the time since the last sync. The **Last sync** sensor shows when that was.

Some of what your device records late in the evening reaches Garmin only with the first sync
after midnight, when the sensors already show the new day. For the day before, the integration
then adds that data to the long-term statistics, so the daily totals there match Garmin
Connect.

Garmin publishes no request limits for the Personal API. Polling more often would not give you
newer data, because the data only changes when your device syncs.

## Known limitations

- The sensors show the current day only. Earlier days are available only through the
  long-term statistics recorded while the integration was running; history from before you
  installed it is not imported.
- Only the day before is corrected after a late sync. If your device does not sync for longer
  than that, the statistics of the earlier days keep the values from before the sync.
- Garmin does not report when a key expires. Home Assistant asks for a new key only after
  Garmin has rejected the old one.
- The Personal API is meant for individuals reading their own data. Each person needs their
  own key.

## Removing the integration

This integration follows standard integration removal:

1. Go to **Settings → Devices & services** and select **Garmin Connect Personal**.
2. Open the menu of the entry and select **Delete**.

The key stays valid in Garmin Connect until it expires. To revoke it straight away, delete it
in Garmin Connect under **Settings → Personal API Key**.

## Troubleshooting

<details>
<summary>Setup fails with "Garmin rejected the key"</summary>

Garmin did not accept the key you pasted. Either part of it is missing, or it has expired or
been deleted. Copy the whole key again; if you no longer have it, create a new one in Garmin
Connect, because Garmin shows a key only once.

</details>

<details>
<summary>Home Assistant asks you to reauthenticate</summary>

Garmin rejected the stored key, usually because it expired or was deleted in Garmin Connect.
The sensors are unavailable until you fix it. Create a new key in Garmin Connect, open the
reauthentication request in **Settings → Devices & services** or **Settings → Repairs**, and
paste the new key.

</details>

<details>
<summary>The values are lower than in the Garmin Connect app</summary>

The app may have newer data than Garmin's servers had at the last poll, or your device has not
synced recently. Check the **Last sync** sensor. Open the Garmin Connect app to start a sync;
the integration picks it up within 10 minutes.

</details>

<details>
<summary>The sensors are unknown shortly after midnight</summary>

Garmin has no data for the new day until your device syncs after midnight. The sensors get
values with the first poll after that sync.

</details>

## Examples

The entity IDs below assume an entry named Garmin Connect. Replace them, and the notify
action, with yours.

### Remind me of my step goal

Sends a notification at 20:00 when you have taken fewer than 8,000 steps.

```yaml
automation:
  - alias: "Step goal reminder"
    triggers:
      - trigger: time
        at: "20:00:00"
    conditions:
      - condition: numeric_state
        entity_id: sensor.garmin_connect_steps
        below: 8000
    actions:
      - action: notify.mobile_app_my_phone
        data:
          message: >-
            {{ states('sensor.garmin_connect_steps') }} steps so far today.
            A short walk still fits in.
```

### Wind down when Body Battery is low

Turns on a wind-down scene in the evening when Body Battery drops below 20.

```yaml
automation:
  - alias: "Wind down on low Body Battery"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.garmin_connect_body_battery
        below: 20
    conditions:
      - condition: time
        after: "18:00:00"
    actions:
      - action: scene.turn_on
        target:
          entity_id: scene.wind_down
```

### Warn when the watch stops syncing

Sends a notification when the device has not synced for 12 hours.

```yaml
automation:
  - alias: "Garmin watch not syncing"
    triggers:
      - trigger: template
        value_template: >-
          {% set last = states('sensor.garmin_connect_last_sync') | as_datetime(none) %}
          {{ last is not none and now() - last > timedelta(hours=12) }}
    actions:
      - action: notify.mobile_app_my_phone
        data:
          message: "The Garmin watch has not synced for 12 hours."
```

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
