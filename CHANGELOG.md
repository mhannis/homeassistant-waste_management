# Changelog

## 0.1.7

- Fix `Error setting up sensor platform: 'offset_days'` for existing configuration entries that do not contain the optional offset field. Missing or null offsets now use zero; configured positive and negative offsets are preserved.
- Default the setup form's optional offset to zero instead of null and tolerate omitted offsets during setup.
- Preserve existing account settings and sensor unique IDs; no account reconfiguration is required for this fix.
- Add dependency-free regression tests for legacy entries and new setup input.

This focused patch does not fix Waste Management authentication errors, HTTP 500/504 responses, or API changes. Tests use mocked external services; successful tests are not proof of live account connectivity.
