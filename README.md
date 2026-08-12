# Desafio #22 — Diagnóstico Preditivo de Bateria (VE): degradação antes do limiar

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/GuilhermeFrick/ev-battery-early-degradation-poc/blob/main/notebooks/PoC_Bateria_Colab.ipynb)

PoC para o desafio *Diagnóstico Preditivo para Powertrain Elétrico*: **detectar
degradação lenta / "quase-falha" antes de um evento de falha**, provado em **dataset
público rotulado** e depois transferível ao VE do patrocinador.

> **Enquadramento honesto (crítico):** não existe dataset público com DTC de VE real.
> Então a PoC prova *"detecção antes do limiar de degradação (SoH/capacidade/resistência)"*
> — **nunca** *"X dias antes do DTC"*. O DTC fica como rótulo a obter com o patrocinador.
> Base desta decisão: levantamento de datasets (nossa análise + Manus, ago/2026).

## Estratégia (bateria primeiro; motor como 2ª trilha)
1. **Trilha principal — previsão precoce de fim de vida (Severson/MIT):** prever a vida
   útil (ciclos) a partir dos **primeiros ~100 ciclos**, *antes* de queda visível de
   capacidade. É o análogo mais puro e reproduzível de "detectar degradação cedo".
2. **Camada EV real — anomalia (EVBattery):** detecção de anomalia de saúde em snippets
   de carga de **EVs reais**, com label de anomalia/capacidade.
3. **Estado de saúde contínuo (SoH):** índice de degradação + regra de alerta por limiar,
   com métricas honestas: **lead time** até o limiar e **falsos alarmes por 1.000 ciclos**.

## Datasets (públicos, licença permissiva)
| Dataset | Papel | Licença | Acesso |
|---|---|---|---|
| **Severson/MIT** (data.matr.io) | previsão precoce de vida | CC BY 4.0 | download público (3 batches .mat) |
| **EVBattery** (Figshare) | anomalia em EV real | CC BY 4.0 | download direto (~1,38 GB) |
| NASA PCoE (B0005/6/7/18) | demo rápida de SoH/RUL | citar | S3 direto (pequeno) |

## Como rodar — **Colab-first** (disco local cheio; e requisito do projeto)
O download e o processamento rodam no **Colab** (não no disco local). Abra
`notebooks/PoC_Bateria_Colab.ipynb` pelo badge acima — ele **baixa o NASA automaticamente**
(espelho S3, sem login/upload manual). O repo versiona **só código** — dados nunca.

```bash
# local (se houver espaço em disco):
pip install -r requirements.txt
python scripts/download_data.py --dataset nasa --out data   # baixa e extrai B0005/6/7/18
python src/run_poc.py --data-dir data
```

### Portabilidade Databricks
Código em pandas/numpy com **I/O isolado** (`src/io_data.py`) para trocar leitura local
por DBFS/Spark sem mexer na lógica de modelagem.

## Estrutura
```
desafio22-bateria-ev-degradacao-precoce/
├── data/           # datasets (Colab/Databricks) — NÃO versionado
├── scripts/        # download_data.py (aquisição documentada)
├── src/            # io_data, features, model, evaluate (código da PoC)
├── notebooks/      # PoC_Bateria_Colab.ipynb (via principal)
├── docs/           # documentação + docs/figuras/*.png
└── results/        # saídas (NÃO versionado)
```

## Métricas honestas (protocolo)
- **Split por célula/veículo e por tempo** (nunca embaralhar snippets do mesmo item).
- **Lead time** até cruzar o limiar de degradação (proxy de "antes da falha").
- **Falsos alarmes / 1.000 ciclos** (ou /1.000 km quando houver campo).
- Onde não há falha real: reportar como *"antes do limiar"*, não *"antes do DTC"*.
