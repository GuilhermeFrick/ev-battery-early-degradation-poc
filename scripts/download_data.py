"""Aquisição de datasets públicos de bateria (Colab/Databricks).

Não fabrica URLs: mantém um registro com página oficial, licença, tamanho e notas,
imprime instruções, e — quando você passar --url de um arquivo direto — faz o download.

Uso:
  python scripts/download_data.py --dataset severson          # instruções
  python scripts/download_data.py --dataset evbattery --url <URL_DIRETO> --out data
"""
from __future__ import annotations
import argparse, os, sys

REGISTRY = {
    "severson": {
        "nome": "Severson/MIT — data-driven battery cycle life",
        "papel": "previsão precoce de fim de vida (antes da queda de capacidade)",
        "pagina": "https://data.matr.io/1/  (Nature Energy 2019; código: rdbraatz/data-driven-prediction-of-battery-cycle-life)",
        "licenca": "CC BY 4.0 (dados)",
        "tamanho": "3 batches .mat (HDF5), ~vários GB no total",
        "notas": "Baixar os 3 batches (2017-05-12, 2017-06-30, 2018-04-12). Rodar no Colab.",
    },
    "evbattery": {
        "nome": "EVBattery / Realistic fault detection (Figshare)",
        "papel": "anomalia de saúde em EV real (snippets de carga rotulados)",
        "pagina": "Figshare (artigo EVBattery / 'Realistic fault detection of Li-ion battery')",
        "licenca": "CC BY 4.0",
        "tamanho": "~1,38 GB (release Figshare; ~690k snippets / 347 EVs)",
        "notas": "Confirme a DOI/URL do arquivo no Figshare e passe em --url.",
    },
    "nasa": {
        "nome": "NASA PCoE Li-ion Battery (B0005/B0006/B0007/B0018)",
        "papel": "demo rápida de SoH/RUL (células de bancada, download pequeno)",
        "pagina": "https://www.nasa.gov/intelligent-systems-division/  (PCoE Prognostics Data Repository)",
        "licenca": "citar a fonte (sem licença OSI explícita)",
        "tamanho": "pequeno (dezenas de MB)",
        "notas": "Bom para validar o pipeline rápido antes de Severson/EVBattery.",
    },
}


def show(ds):
    d = REGISTRY[ds]
    print(f"\n=== {d['nome']} ===")
    for k in ("papel", "pagina", "licenca", "tamanho", "notas"):
        print(f"  {k:8}: {d[k]}")
    print("\n  -> baixe pela página oficial (respeitando a licença) e coloque em --out,")
    print("     ou passe --url de um arquivo direto para baixar aqui.")


def download(url, out):
    import requests
    os.makedirs(out, exist_ok=True)
    fname = os.path.join(out, url.split("/")[-1].split("?")[0] or "download.bin")
    print(f"baixando {url}\n   -> {fname}")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0)); done = 0
        with open(fname, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk); done += len(chunk)
                if total:
                    print(f"\r   {done/1e6:7.1f}/{total/1e6:.1f} MB", end="")
    print("\nok:", fname)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=list(REGISTRY), required=True)
    ap.add_argument("--url", help="URL direto de um arquivo para baixar")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    show(a.dataset)
    if a.url:
        download(a.url, a.out)
    else:
        print("\n(sem --url: apenas instruções acima)")
