"""The payload contract: docs/payload.md, the real CLI payload and what the template reads must agree.

The tables in docs/payload.md are parsed and compared with (1) a payload captured from a real `--demo` CLI run, including `alerts`,
and (2) the fields src/template.html reads. A renamed field, a changed type or an undocumented key fails here.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from dipdash import cli

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "payload.md"
TEMPLATE = ROOT / "src" / "template.html"

# Names the template reads from a row-like variable `r` that are not payload fields (DOM and JS built-ins).
TEMPLATE_ALLOW = {"onclick", "toFixed", "type"}

PY_TYPES = {"str": (str,), "int": (int,), "float": (float, int), "bool": (bool,), "list": (list,), "dict": (dict,)}


# ---------------------------------------------------------------- the documented spec, parsed from docs/payload.md
def parse_doc(text: str) -> dict[str, dict[str, tuple[str, str]]]:
    """{section title: {field: (type, null)}} from the markdown tables (rows that start with a backticked field)."""
    out: dict[str, dict[str, tuple[str, str]]] = {}
    title = None
    for line in text.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            continue
        m = re.match(r"\|\s*`([A-Za-z0-9_]+)`\s*\|\s*(\w+)\s*\|\s*(no|yes|optional)\s*\|", line)
        if m and title:
            out.setdefault(title, {})[m.group(1)] = (m.group(2), m.group(3))
    return out


SPEC = parse_doc(DOC.read_text(encoding="utf-8"))


def check_value(path: str, v, spec: tuple[str, str], problems: list[str]) -> None:
    typ, null = spec
    if v is None:
        if null == "no":
            problems.append(f"{path} is null but documented as never null")
        return
    if isinstance(v, bool) and typ != "bool":
        problems.append(f"{path} is bool, documented {typ}")
    elif not isinstance(v, PY_TYPES[typ]):
        problems.append(f"{path} is {type(v).__name__}, documented {typ}")


def check_dict(path: str, d, section: str, problems: list[str]) -> None:
    spec = SPEC[section]
    if not isinstance(d, dict):
        problems.append(f"{path} is not an object")
        return
    for k in sorted(set(d) - set(spec)):
        problems.append(f"{path}.{k} is in the payload but not in docs/payload.md ({section})")
    for k, s in spec.items():
        if k not in d:
            if s[1] != "optional":
                problems.append(f"{path}.{k} is documented but missing from the payload")
            continue
        check_value(f"{path}.{k}", d[k], s, problems)


def check_payload(p: dict) -> list[str]:
    """Every difference between a payload and the documented contract, as readable lines."""
    problems: list[str] = []
    top = SPEC["Top level"]
    for k in sorted(set(p) - set(top)):
        problems.append(f"top-level {k} is not documented")
    for k, s in top.items():
        if k not in p:
            if k != "alerts":                                    # the only key that may be absent
                problems.append(f"top-level {k} is missing")
            continue
        check_value(k, p[k], s, problems)
    axis = p.get("chart_dates")
    if isinstance(axis, list) and (axis != sorted(set(axis)) or any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(x)) for x in axis)):
        problems.append("chart_dates must be sorted, unique ISO dates")
    for i, r in enumerate(p.get("rows", [])):
        path = f"rows[{i}]"
        check_dict(path, r, "Row", problems)
        if not isinstance(r, dict):
            continue
        for k in ("spark", "why"):
            if isinstance(r.get(k), list) and any(x is None for x in r[k]):
                problems.append(f"{path}.{k} has a null entry")
        if isinstance(r.get("hist"), dict):
            check_dict(f"{path}.hist", r["hist"], "Hist", problems)
            lens = {len(v) for v in r["hist"].values() if isinstance(v, list)}
            if len(lens) > 1:
                problems.append(f"{path}.hist lists have different lengths {sorted(lens)}")
            axis = p.get("chart_dates")
            if isinstance(axis, list) and isinstance(r["hist"].get("c"), list) and isinstance(r["hist"].get("o"), int):
                if r["hist"]["o"] < 0 or r["hist"]["o"] + len(r["hist"]["c"]) > len(axis):
                    problems.append(f"{path}.hist runs outside chart_dates (o={r['hist']['o']}, len={len(r['hist']['c'])}, axis={len(axis)})")
                elif r["hist"]["c"] and (r["hist"]["c"][0] is None or r["hist"]["c"][-1] is None
                                         or axis[r["hist"]["o"] + len(r["hist"]["c"]) - 1] != r.get("asof")):
                    problems.append(f"{path}.hist must start and end on a bar, and end on asof")
        if r.get("prev") is not None:
            check_dict(f"{path}.prev", r["prev"], "Prev", problems)
        if r.get("earn") is not None:
            check_dict(f"{path}.earn", r["earn"], "Earn", problems)
        for j, c in enumerate(r.get("qchecks") or []):
            check_dict(f"{path}.qchecks[{j}]", c, "Quality check", problems)
        for j, n in enumerate(r.get("news") or []):
            check_dict(f"{path}.news[{j}]", n, "Headline", problems)
    for sec, key in (("Index item", "indices"), ("Issue item", "issues"), ("Left-out item", "data_quality")):
        for j, x in enumerate(p.get(key) or []):
            check_dict(f"{key}[{j}]", x, sec, problems)
    for j, a in enumerate(p.get("alerts") or []):
        check_dict(f"alerts[{j}]", a, "Alert item", problems)
    st = p.get("settings")
    if isinstance(st, dict) and set(st) != {"dip", "quality", "knife"}:
        problems.append(f"settings keys are {sorted(st)}, documented dip, quality, knife")
    return problems


def template_reads(html: str) -> dict[str, set[str]]:
    """Field names the template reads: DATA.x, r.x (row), .earn.x and .prev.x."""
    return {"data": set(re.findall(r"\bDATA\.([A-Za-z_]\w*)", html)),
            "row": set(re.findall(r"\br\.([A-Za-z_]\w*)", html)),
            "earn": set(re.findall(r"\.earn\??\.([A-Za-z_]\w*)", html)),
            "prev": set(re.findall(r"\.prev\??\.([A-Za-z_]\w*)", html))}


def check_template(html: str) -> list[str]:
    reads = template_reads(html)
    problems = []
    for name, section, allow in (("data", "Top level", set()), ("row", "Row", TEMPLATE_ALLOW),
                                 ("earn", "Earn", set()), ("prev", "Prev", set())):
        for f in sorted(reads[name] - set(SPEC[section]) - allow):
            problems.append(f"the template reads {name} field '{f}', which docs/payload.md does not list under {section}")
    return problems


# ---------------------------------------------------------------- a real CLI demo run
@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """Run `dipdash --demo` into a temp folder and capture the payload as built and as written to the page."""
    out = tmp_path_factory.mktemp("payload") / "dashboard.html"
    seen: dict = {}
    mp = pytest.MonkeyPatch()
    real_build, real_write = cli.build_payload, cli.write_dashboard

    def build(*a, **k):
        p = real_build(*a, **k)
        seen["keys_after_build"] = set(p)
        return p

    def write(p, path):
        seen["payload"] = p
        return real_write(p, path)

    mp.setattr(cli, "build_payload", build)
    mp.setattr(cli, "write_dashboard", write)
    try:
        assert cli.main(["--demo", "--out", str(out)]) == 0
    finally:
        mp.undo()
    return seen


def test_the_doc_tables_were_parsed():
    assert {"Top level", "Row", "Hist", "Prev", "Earn", "Quality check", "Headline", "Index item", "Issue item",
            "Left-out item", "Alert item"} <= set(SPEC)
    assert len(SPEC["Row"]) >= 40 and "r1" in SPEC["Row"]


def test_the_cli_demo_payload_matches_the_documented_contract(demo):
    p = demo["payload"]
    assert p["demo"] is True and len(p["rows"]) > 0 and isinstance(p["alerts"], list)
    assert check_payload(p) == []


def test_every_documented_row_key_is_present_in_every_row(demo):
    keys = set(SPEC["Row"])
    assert all(set(r) == keys for r in demo["payload"]["rows"])


def test_the_payload_is_strict_json_and_moves_are_fractions(demo):
    p = demo["payload"]
    json.dumps(p, allow_nan=False)                           # NaN or infinity would raise
    assert all(abs(r["r1"]) < 1 and abs(r["r5"]) < 1 for r in p["rows"] if r["r1"] is not None and r["r5"] is not None)
    assert {r["setup"] for r in p["rows"]} <= {"Quality dip", "Falling knife", "Dip, low quality", "Dip, no fundamentals", "No dip"}


def test_the_template_reads_only_documented_fields():
    assert check_template(TEMPLATE.read_text(encoding="utf-8")) == []
    reads = template_reads(TEMPLATE.read_text(encoding="utf-8"))
    assert {"rows", "alerts", "settings"} <= reads["data"] and {"r1", "price", "setup"} <= reads["row"]    # the regexes do find things


# ---------------------------------------------------------------- a rename is caught
def test_a_renamed_row_field_in_the_payload_is_caught(demo):
    p = copy.deepcopy(demo["payload"])
    for r in p["rows"]:
        r["ret1"] = r.pop("r1")
    problems = check_payload(p)
    assert any("ret1" in x and "not in docs" in x for x in problems) and any(".r1 is documented but missing" in x for x in problems)


def test_a_changed_type_or_an_unexpected_null_is_caught(demo):
    p = copy.deepcopy(demo["payload"])
    p["rows"][0]["price"] = "12.3"
    p["rows"][1]["t"] = None
    p["rows"][2]["knife"] = 1
    problems = check_payload(p)
    assert any("price is str" in x for x in problems) and any("t is null" in x for x in problems) and any("knife is" in x for x in problems)


def test_a_renamed_field_in_the_template_is_caught():
    html = TEMPLATE.read_text(encoding="utf-8").replace("r.r1", "r.ret1")
    assert any("'ret1'" in x for x in check_template(html))
    html = TEMPLATE.read_text(encoding="utf-8").replace("DATA.alerts", "DATA.alarms")
    assert any("'alarms'" in x for x in check_template(html))


# ---------------------------------------------------------------- alerts: absent, null, list
def test_alerts_are_absent_until_the_alert_step_adds_them(demo):
    assert "alerts" not in demo["keys_after_build"]
    assert "alerts" in demo["payload"]


def test_a_failed_alert_step_gives_null_not_an_empty_list(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("forced failure")

    monkeypatch.setattr("dipdash.alerts.run_alerts", boom)
    seen = {}
    real = cli.write_dashboard
    monkeypatch.setattr(cli, "write_dashboard", lambda p, path: (seen.setdefault("p", p), real(p, path))[1])
    assert cli.main(["--demo", "--out", str(tmp_path / "dashboard.html")]) == 0
    assert "alerts" in seen["p"] and seen["p"]["alerts"] is None
    assert check_payload(seen["p"]) == []
    assert "could not be evaluated" in (tmp_path / "digest.md").read_text(encoding="utf-8")


def test_setup_text_is_reader_facing_and_never_carries_the_old_wording(demo):
    for r in demo["payload"]["rows"]:
        text = r["setup_text"]
        assert isinstance(text, str) and text
        assert "quality" not in text.lower() and "low quality" not in text.lower()
        if r["setup"] in ("Quality dip", "Dip, low quality") and r["q_applicable"]:
            assert re.fullmatch(r"Dip · passes \d+ of \d+ scored checks( \(\d+ no data\))?", text), text
        if r["setup"] == "Dip, no fundamentals":
            assert text in ("Dip, no fundamentals", "Dip · data looks unreliable")


# ---------------------------------------------------------------- the shared chart axis
def test_every_chart_array_fits_the_shared_axis_in_its_documented_offset_form(demo):
    p = demo["payload"]
    axis, n = p["chart_dates"], len(p["chart_dates"])
    assert n > 0 and p["price_scale"] == 100
    for r in p["rows"]:
        h = r["hist"]
        assert set(h) == {"o", "c", "s", "h"} and len(h["c"]) == len(h["s"]) == len(h["h"])
        assert 0 <= h["o"] and h["o"] + len(h["c"]) <= n                       # the offset form: item i is chart_dates[o + i]
        assert axis[h["o"] + len(h["c"]) - 1] == r["asof"]
        assert h["c"][-1] == round(r["price"] * p["price_scale"]) and len(r["spark"]) == 90
        assert all(isinstance(v, int) for v in r["spark"])


def _old_format_chart_bytes(p: dict) -> int:
    """What hist and spark cost before the shared axis: a dates list per row, float prices, default JSON separators."""
    total, sc = 0, p["price_scale"]
    for r in p["rows"]:
        h, keep = r["hist"], [i for i, v in enumerate(r["hist"]["c"]) if v is not None]
        old = {"d": [p["chart_dates"][h["o"] + i] for i in keep]} | {k: [None if h[k][i] is None else h[k][i] / sc for i in keep] for k in "csh"}
        total += len(json.dumps(old, ensure_ascii=False)) + len(json.dumps([v / sc for v in r["spark"]]))
    return total


def test_the_shared_axis_makes_the_chart_data_at_least_half_smaller(demo):
    p = demo["payload"]
    new = sum(len(json.dumps(r["hist"], separators=(",", ":"))) + len(json.dumps(r["spark"], separators=(",", ":"))) for r in p["rows"])
    old = _old_format_chart_bytes(p)
    assert new <= 0.5 * old, f"chart data is {new:,} bytes, was {old:,} ({new / old:.0%})"


def test_a_broken_axis_is_caught(demo):
    p = copy.deepcopy(demo["payload"])
    p["rows"][0]["hist"]["o"] += 3                                             # runs past the end of the axis
    p["chart_dates"] = list(reversed(p["chart_dates"]))
    problems = check_payload(p)
    assert any("outside chart_dates" in x or "must start and end" in x for x in problems) and any("sorted, unique" in x for x in problems)
