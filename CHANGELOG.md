# Changelog

## 0.1.8

- Reuse Home Assistant's shared HTTP client during sensor updates, avoiding blocking SSL certificate loading on the event loop.
- Await the scheduled refresh and publish the updated state instead of discarding an unawaited coroutine.
- Version 0.1.7 was verified on a live installation: both pickup sensors recovered and returned actual upcoming dates after restart. This does not guarantee connectivity for every WM account.

## 0.1.7

- Fix `Error setting up sensor platform: 'offset_days'` for existing configuration entries that do not contain the optional offset field. Missing or null offsets now use zero; configured positive and negative offsets are preserved.
- Default the setup form's optional offset to zero instead of null and tolerate omitted offsets during setup.
- Preserve existing account settings and sensor unique IDs; no account reconfiguration is required for this fix.
- Add dependency-free regression tests for legacy entries and new setup input.

This focused patch does not fix Waste Management authentication errors, HTTP 500/504 responses, or API changes. Tests use mocked external services; successful tests are not proof of live account connectivity.

## 0.1.9 — retained schedules and adaptive refresh

- One successful live pickup reading per local day; next scheduled fetch at 00:05 the following day in Home Assistant's timezone.
- On failure, retry hourly and retain the last valid timestamp. An explicit update_entity call can still request a manual refresh.
- Restore the value and refresh metadata after a restart. Existing entity setup does not depend on the cloud API being online.
- On upgrade from older versions, recover the latest valid timestamp from up to 14 days of retained recorder history if restore state only contains unavailable. No guessed weekly dates.
- Expose data_stale, last_successful_refresh, last_attempt, next_refresh, last_error and pickup_date_passed attributes. Historical migration does not invent a last-success timestamp.
- Invalid/empty API responses retain the previous schedule and trigger retries. An expired date is never advanced automatically.
- Requests are bounded to 90 seconds. Failed updates log only the stage, exception class and HTTP status.
- Regression tests cover outages/recovery, restart restoration, initial failure, malformed responses, daily/hourly timing, DST, offset preservation, and timer cleanup. Run with Python timezone data installed (pip install tzdata on Windows).

