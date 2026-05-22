# EnergyCAP Emissions Export QA Workbench — v10 Object Resolution

This version makes it explicit whether each QA finding was resolved to an EnergyCAP object.

## New fields

- `object_resolution_status`
- `object_resolution_note`

If fields such as site/account/meter are blank, the app now tells you whether they are not applicable or whether the source report configuration did not include enough hierarchy detail.

## Deploy

Upload only:

- `app.py`
- `requirements.txt`
