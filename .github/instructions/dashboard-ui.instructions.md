---
name: Dashboard UI Conventions
description: Use when editing the single-file dashboard HTML, panel navigation, or browser-side API wiring.
applyTo: "**/*dashboard*.html"
---
# Dashboard UI Conventions

- This project uses a single-file dashboard. Keep related markup, styling, and JavaScript close to the existing panel or feature area.
- Match existing DOM naming conventions such as `panel-*`, `nav-*`, and small helper functions for rendering and polling.
- Any new panel should have a clear API dependency in `server.py`; avoid client-side placeholders that are not backed by endpoints.
- Prefer incremental additions over restructuring the whole dashboard file.
- When adding polling or background refresh, stop polling when the panel is inactive if the current code already follows that pattern.