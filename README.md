# Waste Management for Home Assistant — offset_days fix

This public fork contains **version 0.1.7**, a focused fix for sensors failing to load with `Error setting up sensor platform: 'offset_days'`. Older configuration entries may lack that optional field. This version treats a missing offset as zero and preserves configured offsets and sensor unique IDs.

Based on [Teagan42's integration](https://github.com/Teagan42/homeassistant-waste_management), originally created by [dcmeglio](https://github.com/dcmeglio/homeassistant-waste_management). See [CHANGELOG.md](CHANGELOG.md) for scope and limitations.

### Manual installation or upgrade

1. Back up your Home Assistant configuration and existing `custom_components/waste_management` directory.
2. Download this repository and copy its `custom_components/waste_management` directory into your Home Assistant configuration directory, replacing the existing integration files.
3. Restart Home Assistant to load the updated Python code. Existing Waste Management configuration entries should remain in place; do not delete and recreate them just to apply this fix.
4. Confirm version `0.1.7` in the installed `manifest.json`, then check the pickup sensors and logs. The integration still requires a working Waste Management account and API.

If HACS manages a different fork of this integration, a subsequent HACS update may overwrite this manual patch. Avoid installing two copies of the same `waste_management` integration. This fork is not listed in the default HACS catalog.

### Regression tests

Run `python -m unittest discover -s tests -v`. The tests execute the actual setup methods with mocked Home Assistant and Waste Management dependencies, covering omitted, null, zero, positive, and negative offsets. They do not test the live API or a complete Home Assistant runtime.

### Original project

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
<a href="https://www.buymeacoffee.com/dcmeglio" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="28" width="119"></a>

[Waste Management](https://www.wm.com) integration for Home Assistant

Pull your next pickup date for your trash and recycle from the Waste Managemet API. You will need an account to wm.com for this to work.
