# Dashboard template is generated from src/web/

- Date: 2026-11-05
- Topic: dashboard
- Origin: handed over by the orchestrator (ui-builder change, commit 1773c62)

---

- 2026-11-05: `src/template.html` is generated from the parts in `src/web/` with `python src/web/assemble.py --write`; edit the parts, not the generated file. The unused `:root[data-theme=dark]` token copy was removed until FE-8 re-adds a forced-dark rule. The alerts class names `.more` and `.empty` clashed with other rules and were renamed `.alerts-more` and `.alerts-empty`; only the alerts "more" hover and the phone "unavailable" text alignment changed (commit 1773c62).
