# One file per decision; docs/decisions.md is a generated index

- Date: 2026-11-04
- Topic: docs
- Origin: handed over by the orchestrator 2026-11-04 (OPS-10); chosen by Iiro 2026-11-04 (wave-2 answers, OPS-10 option A); built by docs-steward 2026-11-04, awaiting review and merge

---

- 2026-11-04 (OPS-10): each decision is its own file in `docs/decisions/`; `docs/decisions.md` is a generated topic index, rebuilt with `python tests/test_decisions_index.py --write`; the 54 old entries and 6 review bullets were split by script, text verbatim, and a test checks each appears exactly once.
