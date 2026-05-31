# Métricas de TracePoint — la canasta anti-Goodhart

> **Ley de Goodhart:** *"cuando una medida se vuelve objetivo, deja de ser buena medida."*
> Este documento diseña el sistema de métricas para que el **TQS no se vuelva el
> objetivo** — sino un indicador de salud, acotado por counter-metrics, guardrails
> y proceso. El harness vive en [`scripts/kpi.py`](scripts/kpi.py).

## 0. North Star (el constructo, no un número)

> **Inteligencia OSINT correcta, útil y no dañina.**

El TQS le sirve a esto; no al revés. Si alguna vez el TQS sube pero la calidad real
de las investigaciones no, **se cambia la métrica, no se festeja el número.**

## 1. Por qué un solo número falla — el estado del arte

- **Surrogación** (Choi, Hecht & Tayler, 2012): es no-consciente y *la mera
  existencia de la métrica basta* para que el equipo confunda el proxy con el
  constructo. No alcanza con "tener cuidado" → hace falta estructura.
- **Taxonomía de Goodhart** (Manheim & Garrabrant, 2018) — 4 fallas, 4 defensas:

| Variante | Cómo nos pegaría | Defensa en este diseño |
|---|---|---|
| **Regresional** | F1 sobre pocas cuentas ≠ exactitud real | Intervalos de Wilson (CI95) + N visible |
| **Extremal** | Afinar hasta clavar el set → frágil en la cola | Set `lockbox` congelado + casos sintéticos |
| **Causal** | Subir TQS en el harness ≠ mejor investigación real | Revisión cualitativa de casos reales |
| **Adversarial** | "Mejorar" el número marcando todo `found` | Counter-metrics pareadas + guardrails |

- **Medición pluralista + humano en el loop** (Thomas, 2020): ninguna métrica
  sola captura un objetivo complejo; lo cuantitativo se ancla con juicio humano.
- **North Star + Guardrails + Counter-metrics** (Mixpanel/Eppo/PostHog): foco
  acotado por frenos no negociables.
- **Slices + lockbox** (specification overfitting; *Rip van Winkle's Razor*): el
  agregado esconde clases muertas; el acceso repetido al test set filtra y deja
  de medir generalización.

## 2. La canasta — drivers pareados con counter-metrics

Cada driver que empujamos **arriba** tiene un freno que **no debe degradarse**.
Esa es la defensa directa contra el Goodhart adversarial.

| Driver (↑) | Counter-metric (no degradar) | Qué neutraliza |
|---|---|---|
| **Recall estricto** (hallar lo que existe; abstenerse = fallo) | **Falsa atribución (FAR)** | inflar recall marcando todo `found` |
| **Cobertura** (veredictos decidibles) | **Calibración** (de lo decidido, % correcto) | convertir `unverified`→confianza falsa |
| **Fiabilidad / latencia** | **Fuentes consultadas** | bajar latencia tirando plataformas |
| **Utilidad del brief IA** | **Afirmaciones no respaldadas + densidad de relleno** | IA que suena bien pero inventa o infla (*tokenmaxxing*) |

**TQS (salud, 0–100)** = `0.50·F1 + 0.25·Cobertura + 0.25·Fiabilidad`.
Se reporta **siempre descompuesto**, nunca como número suelto.

### 2.1 Anti-tokenmaxxing del brief IA

La única superficie generativa es el brief que escribe la IA (`modules/ai_analyzer.py`).
*Tokenmaxxing* = inflar la salida (longitud, relleno, falsa exhaustividad) como
proxy de calidad. Lo atacamos en **dos frentes**, no con un límite de longitud
(eso sería Goodhart: un informe corto y denso es bueno, uno largo y vacío es malo):

- **Frente 1 — matar el driver en la fuente (prompt).** `_build_prompt` ya no fuerza
  N secciones fijas: las secciones son **condicionales** ("incluí una sección solo si
  hay evidencia"), exige concisión y densidad, ancla toda afirmación a un hallazgo
  concreto y **prohíbe introducir específicos** (nombres, correos, @usuarios, URLs,
  fechas, ubicaciones) ausentes en los datos recolectados.
- **Frente 2 — medirlo sin volver la longitud el objetivo** ([`modules/brief_quality.py`](modules/brief_quality.py),
  scorer puro). Dos señales que un modelo **no puede satisfacer inflando**:
  - **`unsupported_specifics`** — específicos nombrados en el brief que **no** aparecen
    en los datos = fabricación. Es el **análogo generativo de la falsa atribución** y
    queda atado al guardrail **CARDINAL** (§3). Inflar el texto solo empeora esta señal.
  - **`filler_density`** — muletillas de relleno por **cada 1000 palabras** (densidad,
    no conteo absoluto: un brief largo legítimo no se penaliza si el relleno está diluido).

  Testeado en [`tests/test_brief_quality.py`](tests/test_brief_quality.py) (puro, sin red).

## 3. Guardrails (pisos duros — si se rompen, no hay release)

- 🔴 **Falsa atribución ≤ 5%** — **CARDINAL**. Adjudicar a una persona la cuenta de
  otra es el daño real e irreversible en OSINT. Prioriza precisión sobre recall.
- **Calibración por slice ≥ 70%** (por tipo de plataforma; con N≥3) — el agregado
  no puede tapar que las 8 plataformas `spa` estén muertas.
- **Tasa de error ≤ 20%**.

Umbrales iniciales = *placeholders a calibrar tras consolidar el baseline.*

## 4. Proceso (contra surrogación y overfitting)

- **Dos ground-truths**: [`dev`](scripts/ground_truth.dev.yaml) (iterás libre) y
  [`lockbox`](scripts/ground_truth.lockbox.yaml) (congelado, solo pre-release,
  rotar cada N releases).
- **Intervalos de confianza** (Wilson 95%) sobre FAR y calibración: con N chico el
  punto miente, el CI lo hace visible.
- **Etiquetado humano verificado**: una etiqueta dudosa envenena el KPI. Solo
  cuentas oficiales/públicas o de prueba propias — nunca personas privadas.
- **Revisión cualitativa**: auditar a mano algunas investigaciones reales por ciclo.
- **Auditoría de la métrica**: ¿el TQS sigue correlacionando con "buena
  investigación"? Si no, se rediseña.

## 5. Cómo correrlo

```bash
pip install -r requirements-dev.txt
python scripts/kpi.py --set dev        # itera
python scripts/kpi.py --set lockbox    # juicio pre-release (exit≠0 si rompe guardrail)
```

Cada corrida agrega una línea a `scripts/kpi_history.jsonl` (serie temporal local,
no versionada). El scorer puro está testeado en [`tests/test_kpi.py`](tests/test_kpi.py).

## 6. Baseline (2026-05-31, set `dev`)

| Métrica | Valor | Lectura |
|---|---|---|
| TQS (salud) | 94.44 | **No celebrar**: ver CI |
| F1 / precision / recall | 1.0 / 1.0 / 1.0 | sobre pocas etiquetas |
| Falsa atribución | 0.0 — **CI95 (0.0, 0.43)** | el techo real podría ser 43%: faltan muestras `absent` |
| Calibración | 1.0 — CI95 (0.68, 1.0) | idem |
| Cobertura / Fiabilidad | 0.89 / 0.89 | 1 de 9 chequeos no decidible |

**Conclusión del baseline:** el número es alto pero **estadísticamente no
confiable todavía**. El próximo paso de mejora medible no es "subir el TQS" sino
**ampliar el ground-truth** (más cuentas `present`/`absent` verificadas) hasta que
los intervalos se cierren. Esa es la diferencia entre una métrica y un objetivo.

## Fuentes

- Manheim & Garrabrant, *Categorizing Variants of Goodhart's Law* — [arXiv:1803.04585](https://arxiv.org/abs/1803.04585) · [MIRI](https://intelligence.org/2018/03/27/categorizing-goodhart/)
- Choi, Hecht & Tayler, *Strategy Selection, Surrogation…* (2012), *J. Accounting Research* — [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1475-679X.2012.00465.x) · [Surrogation (Wikipedia)](https://en.wikipedia.org/wiki/Surrogation)
- Thomas, *Reliance on Metrics is a Fundamental Challenge for AI* — [arXiv:2002.08512](https://arxiv.org/abs/2002.08512)
- *Specification overfitting in AI* (2024) — [Springer](https://link.springer.com/article/10.1007/s10462-024-11040-6)
- *Rip van Winkle's Razor* (overfit al test set) — [arXiv:2102.13189](https://arxiv.org/abs/2102.13189)
- Counter-metrics / guardrails — [Mixpanel](https://mixpanel.com/blog/guardrail-metrics/) · [Eppo](https://www.geteppo.com/blog/counter-metrics) · [PostHog](https://posthog.com/product-engineers/guardrail-metrics)
