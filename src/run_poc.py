"""Runner da PoC (local/Colab). Databricks: trocar load_nasa_dir por leitura DBFS.

Uso:  python src/run_poc.py --data-dir data --eol-soh 0.80
"""
from __future__ import annotations
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from battery_poc import (load_nasa_dir, analyze_fleet, summarize,
                         plot_fleet, plot_lead_times)


def main(data_dir, eol_soh, out_dir, fig_dir):
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(fig_dir, exist_ok=True)

    caps = load_nasa_dir(data_dir)
    print("células carregadas:", {c: len(v) for c, v in caps.items()})

    results = analyze_fleet(caps, eol_soh=eol_soh)
    for c, r in results.items():
        print(f"  {c}: EOL={r.eol_idx} alerta={r.alert_idx} lead={r.lead_time} "
              f"falso_alarme={r.false_alarm}")

    summ = summarize(results)
    print("\nRESUMO:", json.dumps(summ, ensure_ascii=False))
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summ, f, ensure_ascii=False, indent=2)

    plot_fleet(results, os.path.join(fig_dir, "soh-alerta.png"))
    plot_lead_times(results, os.path.join(fig_dir, "lead-time.png"))
    print("figuras em", fig_dir)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--eol-soh", type=float, default=0.80)
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--fig-dir", default="docs/figuras")
    a = ap.parse_args()
    main(a.data_dir, a.eol_soh, a.out_dir, a.fig_dir)
