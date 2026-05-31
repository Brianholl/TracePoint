#!/usr/bin/env python3
"""
Harness de métricas de TracePoint — la canasta anti-Goodhart.

El TQS NO es un objetivo: es un indicador de salud que SIEMPRE se muestra
descompuesto, acotado por counter-metrics y guardrails. Ver METRICS.md.

Diseño en dos mitades para que la *matemática* sea testeable sin red:
  - compute_report(checks, cfg)  → PURO (tests en tests/test_kpi.py)
  - collect(ground_truth)        → toca la red (search_username real)

Uso:
    python scripts/kpi.py --set dev          # corre el dev set
    python scripts/kpi.py --set lockbox      # corre el set congelado (pre-release)
    python scripts/kpi.py --set dev --no-net --fixture f.json   # recomputa sin red

Cada corrida agrega una línea a scripts/kpi_history.jsonl (serie temporal).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ─── Vocabulario de veredictos del clasificador ─────────────────────────────
DECIDED_POS = {"found"}
DECIDED_NEG = {"not_found"}
# "decidible" = el sistema se animó a un veredicto binario.
DECIDED = DECIDED_POS | DECIDED_NEG
# fallas operativas (cuentan contra fiabilidad, no son abstenciones honestas).
ERROR_STATUSES = {"timeout", "error", "rate_limited", "blocked"}
# todo lo demás (unverified, redirect_*) es abstención: ni positivo ni negativo.

# ─── Guardrails por defecto (placeholders a calibrar tras el baseline) ──────
DEFAULT_GUARDRAILS = {
    "false_attribution_max": 0.05,   # CARDINAL: nunca atribuir cuenta ajena
    "error_rate_max": 0.20,
    "slice_calibration_min": 0.70,   # por tipo de plataforma
    "slice_min_n": 3,                # mínimo de muestras decididas para evaluar un slice
}

WEIGHTS = {"f1": 0.50, "coverage": 0.25, "reliability": 0.25}


def _wilson(k: int, n: int, z: float = 1.96):
    """Intervalo de confianza de Wilson (95%) para una proporción k/n.

    Con N chico el punto miente; el intervalo hace visible el ruido
    (defensa directa contra el Goodhart regresional)."""
    if n == 0:
        return (None, None)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def _safe_div(a, b):
    return a / b if b else None


def compute_report(checks: list[dict], guardrails: dict | None = None) -> dict:
    """
    Calcula la canasta de métricas a partir de observaciones etiquetadas (PURO).

    Cada check: {platform, ptype, expected: 'present'|'absent', status}
    `positivo` = "la cuenta existe / found".
    """
    g = {**DEFAULT_GUARDRAILS, **(guardrails or {})}

    tp = fp = fn = tn = 0
    present_total = absent_total = 0
    decided = errors = 0
    total = len(checks)

    by_type: dict[str, dict] = {}

    for c in checks:
        status = c["status"]
        expected = c["expected"]
        ptype = c.get("ptype", "?")
        pos = status in DECIDED_POS
        neg = status in DECIDED_NEG

        if status in DECIDED:
            decided += 1
        if status in ERROR_STATUSES:
            errors += 1

        slot = by_type.setdefault(ptype, {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "decided": 0, "n": 0})
        slot["n"] += 1
        if status in DECIDED:
            slot["decided"] += 1

        if expected == "present":
            present_total += 1
            if pos:
                tp += 1; slot["tp"] += 1
            elif neg:
                fn += 1; slot["fn"] += 1
        else:  # absent
            absent_total += 1
            if pos:
                fp += 1; slot["fp"] += 1            # ← FALSA ATRIBUCIÓN
            elif neg:
                tn += 1; slot["tn"] += 1

    # ── Drivers ──
    precision = _safe_div(tp, tp + fp)              # de lo que afirmo "found", ¿cuánto acierto?
    recall = _safe_div(tp, present_total)           # estricto: abstenerse ante un presente = fallo
    p, r = precision or 0.0, recall or 0.0
    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
    coverage = _safe_div(decided, total) or 0.0
    error_rate = errors / total if total else 0.0
    # Sin observaciones, fiabilidad NO es 1.0 ("perfecto"): es indefinida → 0.0.
    reliability = (1 - error_rate) if total else 0.0

    # ── Counter-metrics ──
    false_attribution = _safe_div(fp, absent_total)         # cardinal
    calibration = _safe_div(tp + tn, tp + tn + fp + fn)     # de lo decidido-etiquetado, ¿cuánto correcto?

    # ── TQS (indicador de salud, 0–100) ──
    tqs = round(100 * (WEIGHTS["f1"] * f1
                       + WEIGHTS["coverage"] * coverage
                       + WEIGHTS["reliability"] * reliability), 2)

    # ── Slices por tipo de plataforma ──
    slices = {}
    for ptype, s in sorted(by_type.items()):
        s_decided = s["tp"] + s["tn"] + s["fp"] + s["fn"]
        slices[ptype] = {
            "n": s["n"],
            "decided": s["decided"],
            "calibration": round(_safe_div(s["tp"] + s["tn"], s_decided), 4) if s_decided else None,
            "false_attr": round(_safe_div(s["fp"], s["fp"] + s["tn"]), 4) if (s["fp"] + s["tn"]) else None,
        }

    # ── Guardrails (pisos duros) ──
    guard = []

    def add(name, ok, detail):
        guard.append({"name": name, "ok": bool(ok), "detail": detail})

    add("false_attribution (CARDINAL)",
        false_attribution is None or false_attribution <= g["false_attribution_max"],
        f"{false_attribution} <= {g['false_attribution_max']}")
    if total:
        add("error_rate",
            error_rate <= g["error_rate_max"],
            f"{round(error_rate, 4)} <= {g['error_rate_max']}")
    for ptype, sl in slices.items():
        if sl["decided"] >= g["slice_min_n"] and sl["calibration"] is not None:
            add(f"slice_calibration[{ptype}]",
                sl["calibration"] >= g["slice_calibration_min"],
                f"{sl['calibration']} >= {g['slice_calibration_min']}")

    release_ok = all(x["ok"] for x in guard)

    return {
        "tqs_health": tqs,
        "drivers": {
            "f1": round(f1, 4),
            "precision": round(precision, 4) if precision is not None else None,
            "recall_strict": round(recall, 4) if recall is not None else None,
            "coverage": round(coverage, 4),
            "reliability": round(reliability, 4),
        },
        "counter_metrics": {
            "false_attribution": round(false_attribution, 4) if false_attribution is not None else None,
            "false_attribution_ci95": _wilson(fp, absent_total),
            "calibration": round(calibration, 4) if calibration is not None else None,
            "calibration_ci95": _wilson(tp + tn, tp + tn + fp + fn),
            "sources_consulted": total,
        },
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                      "present": present_total, "absent": absent_total},
        "slices": slices,
        "guardrails": guard,
        "release_ok": release_ok,
        "weights": WEIGHTS,
    }


# ─── Recolección (toca la red) ──────────────────────────────────────────────

def load_ground_truth(path: Path) -> list[dict]:
    import yaml
    with open(path) as f:
        data = yaml.safe_load(f) or []
    return data


async def collect(ground_truth: list[dict]) -> list[dict]:
    """Corre search_username real y arma los checks etiquetados."""
    from modules.search_usernames import search_username, PLATFORMS
    ptype_of = {p["name"].lower(): p.get("type", "text") for p in PLATFORMS}

    checks = []
    for entry in ground_truth:
        username = entry["username"]
        result = await search_username(username)
        status_of = {p["platform"].lower(): p["status"] for p in result.get("profiles", [])}
        for expected, key in (("present", "present"), ("absent", "absent")):
            for platform in entry.get(key, []) or []:
                checks.append({
                    "username": username,
                    "platform": platform,
                    "ptype": ptype_of.get(platform.lower(), "?"),
                    "expected": expected,
                    "status": status_of.get(platform.lower(), "missing"),
                })
    return checks


def render(report: dict, set_name: str) -> str:
    d, cm = report["drivers"], report["counter_metrics"]
    lines = [
        f"═══ TracePoint KPI — set '{set_name}' ═══",
        f"  TQS (salud, NO objetivo): {report['tqs_health']}/100   release_ok={report['release_ok']}",
        "",
        "  DRIVERS                         COUNTER-METRICS",
        f"    F1            {d['f1']}".ljust(34) + f"falsa_atrib   {cm['false_attribution']}  CI95 {cm['false_attribution_ci95']}",
        f"    precision     {d['precision']}".ljust(34) + f"calibración   {cm['calibration']}  CI95 {cm['calibration_ci95']}",
        f"    recall        {d['recall_strict']}".ljust(34) + f"fuentes       {cm['sources_consulted']}",
        f"    coverage      {d['coverage']}",
        f"    reliability   {d['reliability']}",
        "",
        "  SLICES (calibración por tipo):",
    ]
    for ptype, sl in report["slices"].items():
        lines.append(f"    {ptype:<10} n={sl['n']:<3} decididos={sl['decided']:<3} "
                     f"calib={sl['calibration']} falsa_atrib={sl['false_attr']}")
    lines.append("")
    lines.append("  GUARDRAILS:")
    for gd in report["guardrails"]:
        mark = "✓" if gd["ok"] else "✗ FALLA"
        lines.append(f"    [{mark}] {gd['name']}: {gd['detail']}")
    return "\n".join(lines)


async def _amain(args) -> int:
    gt_path = Path(args.fixture) if args.fixture else ROOT / "scripts" / f"ground_truth.{args.set}.yaml"

    if args.no_net:
        # Recompute desde checks ya recolectados (JSON list of checks)
        checks = json.loads(Path(args.fixture).read_text())
    else:
        gt = load_ground_truth(gt_path)
        checks = await collect(gt)

    report = compute_report(checks)
    print(render(report, args.set))

    record = {"ts": dt.datetime.now(dt.UTC).isoformat(), "set": args.set, **report}
    hist = ROOT / "scripts" / "kpi_history.jsonl"
    with open(hist, "a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"\n→ registrado en {hist.relative_to(ROOT)}")

    return 0 if report["release_ok"] else 1


def main():
    ap = argparse.ArgumentParser(description="Harness de métricas de TracePoint (canasta anti-Goodhart)")
    ap.add_argument("--set", default="dev", help="dev | lockbox (default: dev)")
    ap.add_argument("--no-net", action="store_true", help="recomputar desde checks JSON (sin red)")
    ap.add_argument("--fixture", default=None, help="ruta a ground-truth YAML o (con --no-net) a checks JSON")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
