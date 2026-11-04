"""Single source for docs/ROADMAP.md and docs/agents/roadmap-tree.png. Edit here, then run (add --png to redraw the image):
    python docs/agents/roadmap_data.py   (writes the Markdown; the image is rendered from the same data)
"""
# skill short names -> what they are
SKILLS = {
    "dashboard-design": "project skill: layout, visual and verification rules for the page",
    "openbb-data-pull": "project skill: provider checks, caching, validation",
    "backtest-hygiene": "project skill: honest backtests (mandatory for any research claim)",
    "dataviz": "chart form, colour and mark rules",
    "frontend-design": "visual direction for UI",
    "design:accessibility-review": "WCAG check",
    "design:design-critique": "structured design feedback",
    "design:ux-copy": "plain, neutral wording",
    "data:validate-data": "QA of data and analyses",
    "data:statistical-analysis": "statistical methods and uncertainty",
    "engineering:testing-strategy": "what to test and how",
    "engineering:architecture": "decision records and design trade-offs",
    "engineering:documentation": "docs that match the code",
    "engineering:deploy-checklist": "pre-release checks (CI, scheduled run)",
    "engineering:code-review": "review of a diff before merge",
}
# (id, title, builder(s), reviewer(s), skills, depends_on, needs_decision)
WAVES = [
 ("Wave 1 · green suite, two real bugs, first contracts", [
  ("FE-10", "Fix 3 stale browser tests; stable test hooks", "ui-builder", "ui-reviewer", ["dashboard-design", "engineering:testing-strategy"], "", ""),
  ("RES-1", "Digest keeps its backtest caveat (wrong folder picked)", "integrator", "wording-guard, stats-reviewer", ["engineering:testing-strategy", "design:ux-copy"], "", ""),
  ("OPS-5", "Payload documented in docs/payload.md + contract test", "integrator", "ui-reviewer (reads it)", ["openbb-data-pull", "engineering:testing-strategy"], "", ""),
  ("OPS-2 + RES-7", "Clean skips without statsmodels/arch; no hand-typed report numbers", "backtest-analyst", "stats-reviewer", ["backtest-hygiene", "data:statistical-analysis"], "", ""),
  ("OPS-4 + OPS-3", "Runtime vs dev requirements with pins; GitHub Actions CI", "test-engineer", "engineering:code-review pass", ["engineering:testing-strategy", "engineering:deploy-checklist"], "", ""),
  ("DATA-2", "Universe tests offline + verify_universe.py for a live check", "universe-curator", "stats-reviewer (coverage)", ["openbb-data-pull", "data:validate-data"], "", ""),
  ("DATA-7", "One exchange registry (fixes Lisbon earnings time zone)", "data-engineer", "-", ["openbb-data-pull", "engineering:testing-strategy"], "", ""),
  ("RES-13 + RES-12c", "One setup-label function; dd52 known-answer test", "screen-logic", "stats-reviewer", ["backtest-hygiene", "engineering:testing-strategy"], "", ""),
  ("OPS-9 + OPS-11", "Stale numbers in docs; say which demo page is canonical", "docs-steward", "wording-guard", ["engineering:documentation"], "", ""),
 ]),
 ("Wave 2 · foundations", [
  ("DATA-1", "Typed data sources + fake provider; live branch tested offline", "data-engineer → integrator", "-", ["openbb-data-pull", "engineering:testing-strategy"], "", ""),
  ("FE-3 + FE-4 + FE-7", "Stale-data banner, visible error state, small page bugs", "ui-builder", "ui-reviewer, wording-guard", ["dashboard-design", "dataviz", "design:accessibility-review"], "FE-10", ""),
  ("FE-13", "Visual-regression screenshots + DOM-id contract", "ui-builder", "ui-reviewer", ["dashboard-design", "engineering:testing-strategy"], "FE-3", ""),
  ("RES-4", "One pre-registration and trial registry", "backtest-analyst", "stats-reviewer", ["backtest-hygiene", "data:statistical-analysis"], "", ""),
  ("RES-2", "Quality score honesty: scored on n/6, 'distorted', must-pass", "screen-logic", "stats-reviewer, wording-guard", ["backtest-hygiene", "data:statistical-analysis"], "", "D1"),
  ("OPS-6 + OPS-7", "tasks.py one-command checks; pre-commit wording and data guards", "test-engineer", "wording-guard", ["engineering:testing-strategy"], "OPS-3", ""),
  ("OPS-10 + OPS-8", "Decision-log index; 'working in parallel' in CLAUDE.md", "docs-steward", "-", ["engineering:documentation"], "", "D5"),
  ("DATA-10", "Nightly .bat: one retry, log rotation", "ops-runner", "-", ["engineering:deploy-checklist"], "", ""),
 ]),
 ("Wave 3 · structure", [
  ("FE-11 + FE-12", "Split the page into src/web/ parts built into one file; CSS/JS cleanup", "ui-builder → integrator", "ui-reviewer", ["dashboard-design", "frontend-design", "engineering:architecture"], "FE-13", ""),
  ("DATA-3 → DATA-6", "Batched price pull with retries; fundamentals retry + stale flag", "data-engineer", "-", ["openbb-data-pull", "data:validate-data"], "DATA-1", ""),
  ("RES-6 + RES-8", "Provenance in every spec; one shared out-of-sample split", "backtest-analyst", "stats-reviewer", ["backtest-hygiene"], "RES-4", ""),
  ("RES-3", "Dashboard and backtest share one quality function", "screen-logic", "stats-reviewer", ["backtest-hygiene"], "RES-2", ""),
  ("OPS-13", "Windows smoke job in CI", "test-engineer", "-", ["engineering:deploy-checklist"], "OPS-3", ""),
 ]),
 ("Wave 4 · page and data-quality features", [
  ("FE-1 + FE-2", "Table above the fold; sticky header; first 25 rows + Show all", "ui-builder", "ui-reviewer", ["dashboard-design", "dataviz", "design:design-critique"], "FE-11", ""),
  ("FE-14", "Smaller payload (shared date axis)", "integrator → ui-builder", "ui-reviewer", ["engineering:architecture", "dashboard-design"], "OPS-5, FE-11", ""),
  ("DATA-4 + DATA-5 + DATA-8", "Completeness guards, exchange-aware partial bars, coverage report", "data-engineer → integrator", "wording-guard", ["openbb-data-pull", "data:validate-data"], "DATA-1, DATA-7", ""),
  ("DATA-12 + DATA-14", "Cross-check sampling and reasons; consistent index fetch", "data-engineer", "-", ["openbb-data-pull"], "DATA-4", ""),
  ("RES-9", "Beta standard error; 'not market-adjusted' when floored", "screen-logic → integrator → ui-builder", "stats-reviewer, ui-reviewer", ["backtest-hygiene", "data:statistical-analysis"], "RES-4", ""),
  ("RES-12a", "Calibrate bootstrap and placebo on null universes", "backtest-analyst", "stats-reviewer", ["backtest-hygiene", "data:statistical-analysis"], "", ""),
  ("FE-5 + FE-6 + FE-8", "Keyboard/touch chart details; print style; filters in URL; theme toggle", "ui-builder", "ui-reviewer", ["dashboard-design", "design:accessibility-review"], "FE-1", ""),
 ]),
 ("Wave 5 · honest claims and long-run research", [
  ("RES-11", "Claims contract: neutral labels, no score sort, 'What testing found' box", "docs-steward → integrator → ui-builder", "wording-guard, stats-reviewer", ["design:ux-copy", "backtest-hygiene", "dashboard-design"], "RES-4", "D2"),
  ("RES-5", "Forward ledger: a true holdout without survivorship", "backtest-analyst → integrator", "stats-reviewer", ["backtest-hygiene"], "RES-4", ""),
  ("RES-10", "Delisted names + survivorship stress bound", "backtest-analyst, universe-curator", "stats-reviewer", ["backtest-hygiene", "data:validate-data"], "RES-4", "D4"),
  ("DATA-9", "Raw-data retention (dry run, archive)", "data-engineer", "-", ["openbb-data-pull"], "", "D3"),
  ("DATA-13", "European earnings coverage; manual overrides file", "data-engineer", "-", ["openbb-data-pull"], "DATA-7", ""),
  ("OPS-12", "One browser helper for tests and screenshots; CI uploads PNGs", "test-engineer → ui-builder", "-", ["engineering:testing-strategy"], "OPS-3, FE-13", ""),
 ]),
]
DECISIONS = [
 ("D1", "Which quality checks must always pass", "RES-2"),
 ("D2", "Neutral label instead of 'Quality dip'; no default sort by score", "RES-11"),
 ("D3", "Raw-data retention policy", "DATA-9"),
 ("D4", "What to do with tickers the checker flags", "RES-10, universe changes"),
 ("D5", "Approve the 'working in parallel' text for CLAUDE.md", "OPS-8"),
]

def markdown() -> str:
    out = ["# Roadmap: every required step, who does it, with which skills", "",
           "Generated from `docs/agents/roadmap_data.py` (edit there). Agents are defined in `.claude/agents/`; how a wave runs is in",
           "`docs/AGENTS.md`; detail and status per item are in `docs/BACKLOG.md`. Wave-1 implementation plans are in `docs/plans/wave-1/`,",
           "decision briefs in `docs/plans/decisions.md`. Later waves are planned when they start, so their plans match the code.", "",
           "![Roadmap tree](agents/roadmap-tree.png)", "",
           "Every task follows the same loop: **plan** (a read-only planner applies CLAUDE.md Rule 1) → **build** (the owner agent) →",
           "**review** (a read-only reviewer that did not write it) → **merge** (orchestrator, full test run, backlog update).", "",
           "## Your decisions first", ""]
    out += [f"- **{d}** {t} → unblocks {u}" for d, t, u in DECISIONS]
    for wave, items in WAVES:
        out += ["", f"## {wave}", ""]
        for i, t, b, r, sk, dep, dec in items:
            extra = (f" · after {dep}" if dep else "") + (f" · waits for {dec}" if dec else "")
            plan = ""
            if wave.startswith("Wave 1"):
                plan = f" · plan: [`docs/plans/wave-1/{i.split(' ')[0]}.md`](plans/wave-1/{i.split(' ')[0]}.md)"
            out += [f"- **{i}**: {t}{extra}{plan}",
                    f"  - builder: `{b}` · reviewer: {r}",
                    f"  - skills: {', '.join('`'+s+'`' for s in sk)}"]
    out += ["", "## Skills used, and what each is for", ""]
    out += [f"- `{k}`: {v}" for k, v in SKILLS.items()]
    return "\n".join(out) + "\n"

PROJECT_SKILLS = {"dashboard-design", "openbb-data-pull", "backtest-hygiene"}


def html(plans_dir) -> str:
    """The roadmap tree as one HTML page (rendered to agents/roadmap-tree.png with --png). Plain stdlib, no dependencies."""
    from html import escape as e
    css = """
    body{font:15px/1.4 Arial,Helvetica,sans-serif;color:#141821;background:#fff;margin:24px;width:1900px}
    h1{font-size:26px;margin:0 0 4px} .sub{color:#4a5263;margin:0 0 16px}
    .top{display:grid;grid-template-columns:330px repeat(5,1fr);gap:10px;margin-bottom:14px}
    .orch{background:#4a3fb5;color:#fff;border-radius:10px;padding:14px 16px}
    .orch b{font-size:18px} .orch .s{font-size:13px;opacity:.95;margin:2px 0 10px}
    .loop{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
    .loop span{background:#fff;color:#2b2470;font-weight:600;font-size:13px;border-radius:6px;padding:3px 9px}
    .loop i{font-style:normal;color:#fff}
    .dec{background:#fdf6e3;border:1.5px dashed #a87400;border-radius:10px;padding:10px 12px;font-size:14px}
    .dec .u{color:#7a5200;font-size:13px;margin-top:4px}
    .waves{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;align-items:start}
    .wh{background:#e9e7f8;border-radius:10px;padding:10px 12px;margin-bottom:8px}
    .wh b{font-size:17px} .wh div{color:#4a5263;font-size:13.5px}
    .card{border:1.5px solid #c4cad4;border-radius:10px;padding:10px 12px;margin-bottom:8px;background:#fff}
    .card.wait{border-style:dashed;border-color:#a87400;background:#fffcf3}
    .id{font-family:Menlo,Consolas,monospace;font-weight:700;color:#3a2fa0;font-size:14px}
    .t{margin:3px 0 6px} .r{font-size:13.5px;color:#2d3340} .r b{color:#4a5263;display:inline-block;width:52px}
    .sk{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
    .sk span{font-size:12px;border-radius:5px;padding:2px 7px;background:#eef0f4;color:#2d3340}
    .sk span.p{background:#e3f3e8;color:#0d5a24}
    .meta{font-size:13px;color:#4a5263;margin-top:6px} .w{color:#7a5200;font-weight:700}
    .ok{color:#0d5a24;font-weight:700}
    .foot{color:#4a5263;font-size:13.5px;margin-top:12px}"""
    out = [f"<!doctype html><meta charset=utf-8><style>{css}</style>",
           "<h1>Roadmap: required steps, subagents and skills</h1>",
           "<p class=sub>Every card runs the same loop. Green skills are the project's own; grey are plugin skills. "
           "Dashed cards wait for one of your decisions. ✓ plan ready = a written plan in docs/plans/wave-1/.</p><div class=top>",
           "<div class=orch><b>orchestrator</b><div class=s>main session · plans waves, dispatches, merges</div><div class=loop>"
           "<span>plan</span><i>→</i><span>build</span><i>→</i><span>review</span><i>→</i><span>merge</span></div></div>"]
    out += [f"<div class=dec><b>{d}</b> {e(t)}<div class=u>→ unblocks {e(u)}</div></div>" for d, t, u in DECISIONS]
    out.append("</div><div class=waves>")
    for wave, items in WAVES:
        num, _, desc = wave.partition(" · ")
        out.append(f"<div><div class=wh><b>{e(num)}</b><div>{e(desc)}</div></div>")
        for i, t, b, r, sk, dep, dec in items:
            planned = wave.startswith("Wave 1") and (plans_dir / f"{i.split(' ')[0]}.md").exists()
            chips = "".join(f"<span class={'p' if s in PROJECT_SKILLS else 'g'}>{e(s)}</span>" for s in sk)
            meta = []
            if dep:
                meta.append(f"after {e(dep)}")
            if planned:
                meta.append("<span class=ok>✓ plan ready</span>")
            if dec:
                meta.append(f"<span class=w>⏸ waits for {dec}</span>")
            out.append(f"<div class='card{' wait' if dec else ''}'><div class=id>{e(i)}</div><div class=t>{e(t)}</div>"
                       f"<div class=r><b>build</b>{e(b)}</div><div class=r><b>review</b>{e(r)}</div>"
                       f"<div class=sk>{chips}</div>" + (f"<div class=meta>{' · '.join(meta)}</div>" if meta else "") + "</div>")
        out.append("</div>")
    out.append("</div><p class=foot>plan = read-only planner applying CLAUDE.md Rule 1 · build = owner agent (→ = handed on in that order) · "
               "review = read-only agent that did not write the change · merge = full test run + backlog update</p>")
    return "".join(out)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    docs = Path(__file__).resolve().parents[1]
    docs.joinpath("ROADMAP.md").write_text(markdown(), encoding="utf-8")
    print("wrote docs/ROADMAP.md")
    if "--png" in sys.argv:                      # needs Playwright + Chromium (dev only)
        from playwright.sync_api import sync_playwright
        page_html = html(docs / "plans" / "wave-1")
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1950, "height": 1000}, device_scale_factor=1.5)
            pg.set_content(page_html)
            pg.screenshot(path=str(docs / "agents" / "roadmap-tree.png"), full_page=True)
            b.close()
        print("wrote docs/agents/roadmap-tree.png")
