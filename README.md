# Faire Day Planner

Installable, offline-capable day planner for the Texas Renaissance Festival.

- `index.html`, `sw.js`, `manifest.webmanifest`: the app and its offline support
- `data.js`: show schedule and shop listings, rebuilt every morning by `tools/update_data.py`
- `tools/overrides.json`: details the festival page does not give (adult shows, show lengths, names)
- `.github/workflows/update.yml`: the daily job that refreshes data and publishes the site

Run it by hand: Actions tab, "Update festival data and publish", Run workflow.
