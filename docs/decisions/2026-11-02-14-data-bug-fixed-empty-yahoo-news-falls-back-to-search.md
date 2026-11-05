# Bug fixed: empty Yahoo news falls back to search

- Date: 2026-11-02
- Topic: data
- Origin: migrated, old entry 17 of 54 (text verbatim)

---

- 2026-11-02 (M2) BUG FOUND: Yahoo's per-ticker `news` list returns empty and the seed swallowed that silently, so the dashboard would have shown no
  headlines. Now falls back to Yahoo search, and a `news_unavailable` warning is logged if no faller gets any headline. Still no headlines for 6 of 14
  fallers, all non-US: search by ticker finds nothing for them, and search by company name returns loosely related articles (the Siemens query returned an
  unrelated company), which could mislead. Left as is; revisit in M3 (e.g. keep only headlines that mention the company).
