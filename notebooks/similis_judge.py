# Databricks notebook — LLM-as-judge para qualidade de recomendações do Similis
# =============================================================================
# OBJETIVO: parar de revisar 315 subcategorias no olho. Este wrapper mantém o
# uso interativo no Databricks, enquanto a implementação testável vive em
# `parts.judge`.
#
# FLUXO recomendado:
#   1. (uma vez) MODO CALIBRAÇÃO: rotule ~150 pares à mão, rode o juiz nos mesmos,
#      cheque o kappa. Só confie no juiz se concordância for alta (kappa >= ~0.6).
#   2. MODO SCAN: roda nas 315, grava veredito por par e o ranking por subcategoria.
#   3. Você abre o ranking, pega o topo (alta taxa_seguranca) e trata com a régua
#      artesanal (hard_filter / filtro de universo). O resto roda com default.
# =============================================================================

from pathlib import Path
import sys

try:
    SIMILIS_ROOT = Path(__file__).resolve().parents[1]
except NameError:
    SIMILIS_ROOT = Path.cwd()
    if SIMILIS_ROOT.name == "notebooks":
        SIMILIS_ROOT = SIMILIS_ROOT.parent
if str(SIMILIS_ROOT) not in sys.path:
    sys.path.insert(0, str(SIMILIS_ROOT))

from parts.judge import *  # noqa: F401,F403,E402


# Para rodar nas 315:
# rodar_scan(spark)
# Para um piloto barato antes (só 2 subcategorias que você conhece):
# rodar_scan(spark, filtro_subcategoria=["formula_infantil", "leite_em_po"])
