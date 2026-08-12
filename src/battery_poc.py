"""PoC — degradação de bateria e alerta precoce (antes do limiar).

Núcleo reutilizável (local, Colab e Databricks). Toda leitura de arquivo fica isolada
em load_* para facilitar a troca por DBFS/Spark no Databricks; a lógica de
degradação/alerta/métrica é numpy puro e não muda entre ambientes.

Fluxo:
  capacidade por ciclo -> SoH -> limiar de fim de vida (EOL) ->
  detector de alerta precoce (projeção da tendência) -> lead time / falsos alarmes.

Enquadramento honesto: como não há DTC em dado público, o "evento" é o cruzamento do
LIMIAR DE DEGRADAÇÃO (SoH/capacidade). Reporta-se "alerta antes do limiar", não "antes do DTC".
"""
from __future__ import annotations
import glob
import os
from dataclasses import dataclass, field

import numpy as np

# ----------------------------------------------------------------------------- #
# 1) LEITURA (isolada — trocar por DBFS/Spark no Databricks)
# ----------------------------------------------------------------------------- #
def load_nasa_cell(path: str) -> np.ndarray:
    """Lê um .mat do NASA PCoE (B0005/6/7/18) e devolve a CAPACIDADE de descarga
    por ciclo de descarga (Ah), na ordem cronológica.

    Usa scipy simplify_cells=True (scipy>=1.5): a struct MATLAB vira dict/list aninhados.
    """
    from scipy.io import loadmat

    m = loadmat(path, simplify_cells=True)
    key = next(k for k in m if not k.startswith("__"))
    cycles = m[key]["cycle"]
    if isinstance(cycles, dict):           # caso raro de 1 ciclo só
        cycles = [cycles]
    caps = []
    for c in cycles:
        if str(c.get("type", "")).lower() != "discharge":
            continue
        data = c.get("data", {})
        cap = data.get("Capacity", None)
        if cap is None:
            continue
        cap = float(np.atleast_1d(cap).ravel()[0])
        if np.isfinite(cap) and cap > 0:
            caps.append(cap)
    return np.asarray(caps, dtype=float)


def load_nasa_dir(data_dir: str, cells=("B0005", "B0006", "B0007", "B0018")) -> dict[str, np.ndarray]:
    """Carrega várias células a partir de um diretório com os .mat."""
    out = {}
    for name in cells:
        hits = glob.glob(os.path.join(data_dir, f"{name}*.mat"))
        if not hits:
            continue
        caps = load_nasa_cell(hits[0])
        if caps.size:
            out[name] = caps
    if not out:
        raise FileNotFoundError(
            f"Nenhum .mat NASA encontrado em {data_dir!r}. Esperado B0005.mat etc."
        )
    return out


# ----------------------------------------------------------------------------- #
# 2) SAÚDE (SoH) E FIM DE VIDA (EOL)
# ----------------------------------------------------------------------------- #
def soh_from_capacity(capacity: np.ndarray, nominal: float | None = None) -> np.ndarray:
    """SoH = capacidade / capacidade de referência. nominal=None usa a 1ª capacidade."""
    capacity = np.asarray(capacity, float)
    ref = float(nominal) if nominal else float(capacity[0])
    return capacity / ref


def eol_index(soh: np.ndarray, eol_soh: float = 0.80) -> int | None:
    """Primeiro ciclo em que o SoH cai a/abaixo do limiar de fim de vida.
    Retorna None se a célula nunca cruza o limiar no histórico."""
    below = np.where(soh <= eol_soh)[0]
    return int(below[0]) if below.size else None


# ----------------------------------------------------------------------------- #
# 3) ALERTA PRECOCE (projeção da tendência recente até o limiar)
# ----------------------------------------------------------------------------- #
@dataclass
class WarningResult:
    cell: str
    eol_idx: int | None
    alert_idx: int | None
    lead_time: int | None            # ciclos entre alerta e EOL
    false_alarm: bool                # alertou numa célula que nunca cruza o limiar
    too_early: bool                  # alertou muito cedo (lead maior que o esperado)
    soh: np.ndarray = field(repr=False)
    eol_soh: float = 0.80


def early_warning(
    soh: np.ndarray,
    eol_soh: float = 0.80,
    window: int = 20,
    rul_warn: int = 50,
    smooth: int = 5,
) -> WarningResult:
    """Dispara alerta quando a tendência recente projeta cruzar o EOL em <= rul_warn ciclos.

    - Ajusta uma reta nos últimos `window` ciclos do SoH (suavizado) e extrapola até `eol_soh`.
    - `false_alarm`: alertou, mas a célula nunca cruza o limiar (não houve evento).
    - `too_early`: alertou com lead time > 2x a janela de aviso pretendida (rul_warn).
    """
    soh = np.asarray(soh, float)
    n = len(soh)
    s = _moving_avg(soh, smooth)
    eol = eol_index(soh, eol_soh)

    alert_idx = None
    for i in range(window, n):
        y = s[i - window:i]
        x = np.arange(window)
        slope, intercept = np.polyfit(x, y, 1)
        if slope >= -1e-6:                      # ainda não está caindo
            continue
        # ciclos à frente até y chegar em eol_soh, a partir do ponto atual (x=window-1)
        cur = intercept + slope * (window - 1)
        rul_hat = (eol_soh - cur) / slope       # slope<0 -> positivo se cur>eol_soh
        if 0 <= rul_hat <= rul_warn:
            alert_idx = i
            break

    lead = (eol - alert_idx) if (eol is not None and alert_idx is not None) else None
    false_alarm = bool(alert_idx is not None and eol is None)
    too_early = bool(lead is not None and lead > 2 * rul_warn)
    return WarningResult("", eol, alert_idx, lead, false_alarm, too_early, soh, eol_soh)


def _moving_avg(x: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return x
    kernel = np.ones(k) / k
    return np.convolve(x, kernel, mode="same")


# ----------------------------------------------------------------------------- #
# 4) ORQUESTRAÇÃO + MÉTRICAS
# ----------------------------------------------------------------------------- #
def analyze_fleet(caps_by_cell: dict[str, np.ndarray], eol_soh=0.80, **kw) -> dict[str, WarningResult]:
    res = {}
    for cell, cap in caps_by_cell.items():
        soh = soh_from_capacity(cap)
        wr = early_warning(soh, eol_soh=eol_soh, **kw)
        wr.cell = cell
        res[cell] = wr
    return res


def summarize(results: dict[str, WarningResult]) -> dict:
    leads = [r.lead_time for r in results.values() if r.lead_time is not None]
    detected = sum(1 for r in results.values() if r.eol_idx is not None and r.alert_idx is not None)
    return {
        "celulas": len(results),
        "com_eol": sum(1 for r in results.values() if r.eol_idx is not None),
        "alertas_antes_do_eol": detected,
        "lead_time_medio_ciclos": round(float(np.mean(leads)), 1) if leads else None,
        "lead_time_min_ciclos": int(np.min(leads)) if leads else None,
        "falsos_alarmes": int(sum(r.false_alarm for r in results.values())),
        "alertas_muito_cedo": int(sum(r.too_early for r in results.values())),
    }


# ----------------------------------------------------------------------------- #
# 5) FIGURAS
# ----------------------------------------------------------------------------- #
def plot_fleet(results: dict[str, WarningResult], out_path: str | None = None):
    """SoH por ciclo de cada célula, com limiar EOL, ponto de alerta e ponto de EOL."""
    import matplotlib.pyplot as plt

    cells = list(results)
    ncol = min(2, len(cells))
    nrow = int(np.ceil(len(cells) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(6.2 * ncol, 3.4 * nrow), squeeze=False)
    for ax, cell in zip(axes.ravel(), cells):
        r = results[cell]
        soh = r.soh
        ax.plot(soh, color="#1f4e79", lw=1.4, label="SoH")
        ax.axhline(r.eol_soh, color="#B23B3B", ls="--", lw=1,
                   label=f"limiar EOL ({r.eol_soh:.0%})")
        if r.eol_idx is not None:
            ax.axvline(r.eol_idx, color="#B23B3B", lw=1, alpha=.6)
            ax.plot(r.eol_idx, soh[r.eol_idx], "o", color="#B23B3B", ms=6)
        if r.alert_idx is not None:
            ax.axvline(r.alert_idx, color="#B45309", lw=1.4)
            ax.plot(r.alert_idx, soh[r.alert_idx], "^", color="#B45309", ms=8,
                    label=f"alerta (lead {r.lead_time} ciclos)" if r.lead_time else "alerta")
        ax.set_title(cell); ax.set_xlabel("ciclo"); ax.set_ylabel("SoH")
        ax.legend(fontsize=7)
    for ax in axes.ravel()[len(cells):]:
        ax.axis("off")
    fig.suptitle("Degradação de bateria: alerta ANTES do limiar de fim de vida", y=1.02)
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=130, bbox_inches="tight")
    return fig


def plot_lead_times(results: dict[str, WarningResult], out_path: str | None = None):
    """Barra do lead time (ciclos de antecedência) por célula."""
    import matplotlib.pyplot as plt

    cells = [c for c, r in results.items() if r.lead_time is not None]
    leads = [results[c].lead_time for c in cells]
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    ax.bar(cells, leads, color="#2E7D5B")
    for c, v in zip(cells, leads):
        ax.text(c, v, str(v), ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("lead time (ciclos antes do EOL)")
    ax.set_title("Antecedência do alerta por célula")
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=130, bbox_inches="tight")
    return fig


if __name__ == "__main__":
    # smoke test sintético (sem dado): curva de degradação decrescente + ruído
    rng = np.random.default_rng(0)
    cyc = np.arange(160)
    cap = 2.0 * np.exp(-cyc / 220) - 0.0008 * np.clip(cyc - 90, 0, None) + rng.normal(0, 0.004, cyc.size)
    r = early_warning(soh_from_capacity(cap), eol_soh=0.80)
    print("EOL idx:", r.eol_idx, "| alerta idx:", r.alert_idx, "| lead:", r.lead_time,
          "| falso alarme:", r.false_alarm, "| muito cedo:", r.too_early)
