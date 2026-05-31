"""
Tests del scorer puro de scripts/kpi.py (la matemática de la canasta).

Sin red: alimenta `compute_report` con checks sintéticos y verifica el
cálculo de drivers, counter-metrics, slices y guardrails. Que el KPI no se
calcule mal es, en sí, una defensa anti-Goodhart.
"""
import importlib.util
from pathlib import Path

import pytest

# kpi.py vive en scripts/ (no es un paquete) → import por ruta
_spec = importlib.util.spec_from_file_location(
    "kpi", Path(__file__).resolve().parent.parent / "scripts" / "kpi.py")
kpi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kpi)


def chk(expected, status, ptype="404"):
    return {"platform": "X", "ptype": ptype, "expected": expected, "status": status}


def test_perfect_classifier():
    checks = [
        chk("present", "found"),
        chk("present", "found"),
        chk("absent", "not_found"),
        chk("absent", "not_found"),
    ]
    r = kpi.compute_report(checks)
    assert r["drivers"]["precision"] == 1.0
    assert r["drivers"]["recall_strict"] == 1.0
    assert r["drivers"]["f1"] == 1.0
    assert r["counter_metrics"]["false_attribution"] == 0.0
    assert r["counter_metrics"]["calibration"] == 1.0
    assert r["release_ok"] is True


def test_false_attribution_breaks_cardinal_guardrail():
    # Marca como 'found' una cuenta que NO existe → falsa atribución 100%
    checks = [chk("absent", "found") for _ in range(4)]
    r = kpi.compute_report(checks)
    assert r["counter_metrics"]["false_attribution"] == 1.0
    cardinal = next(g for g in r["guardrails"] if "CARDINAL" in g["name"])
    assert cardinal["ok"] is False
    assert r["release_ok"] is False


def test_coverage_counts_abstentions():
    # 2 decididos de 4 → coverage 0.5; 'unverified' no es decidible
    checks = [
        chk("present", "found"),
        chk("absent", "not_found"),
        chk("present", "unverified"),
        chk("absent", "unverified"),
    ]
    r = kpi.compute_report(checks)
    assert r["drivers"]["coverage"] == 0.5


def test_strict_recall_punishes_abstention():
    # Abstenerse ante un presente cuenta como no-recuperado
    checks = [chk("present", "found"), chk("present", "unverified")]
    r = kpi.compute_report(checks)
    assert r["drivers"]["recall_strict"] == 0.5


def test_reliability_drops_with_errors():
    checks = [
        chk("present", "found"),
        chk("absent", "timeout"),
        chk("absent", "blocked"),
        chk("present", "error"),
    ]
    r = kpi.compute_report(checks)
    assert r["drivers"]["reliability"] == 0.25       # 3 de 4 son fallas operativas


def test_calibration_gaming_is_caught():
    # "Resolver" abstenciones inventando veredictos sube coverage pero
    # hunde calibración → el guardrail de slice lo detecta.
    checks = [chk("absent", "found", ptype="spa") for _ in range(4)]  # todo mal
    r = kpi.compute_report(checks)
    assert r["slices"]["spa"]["calibration"] == 0.0
    slice_guard = [g for g in r["guardrails"] if "slice_calibration[spa]" in g["name"]]
    assert slice_guard and slice_guard[0]["ok"] is False


def test_wilson_interval_widens_with_small_n():
    lo_small, hi_small = kpi._wilson(1, 2)
    lo_big, hi_big = kpi._wilson(50, 100)
    assert (hi_small - lo_small) > (hi_big - lo_big)   # N chico → más incertidumbre


def test_empty_checks_do_not_crash():
    r = kpi.compute_report([])
    assert r["tqs_health"] == 0.0
    assert r["release_ok"] is True
