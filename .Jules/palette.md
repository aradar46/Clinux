## 2026-09-04 - Accessible ARIA labels for retro symbol buttons
**Learning:** In retro/ASCII software interfaces, icon-only and single-character control buttons (like `?`, `_`, `□`, `X`) lack accessible text for screen readers and tooltips for mouse hover.
**Action:** Always complement retro symbol controls with explicit `aria-label` and `title` attributes, and bind header text labels to input controls using explicit `<label for="...">` associations.
