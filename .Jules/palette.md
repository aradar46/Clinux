## 2026-09-03 - Accessible Window Controls in Retro Desktop UIs
**Learning:** In retro window container designs using single-character symbols (`?`, `_`, `□`, `X`) for titlebars and modal headers, controls are unreadable to screen readers without explicit ARIA attributes.
**Action:** Always pair symbol-only `.win-btn` elements with descriptive `aria-label` and `title` attributes so screen reader users receive context while preserving the authentic vintage appearance.
