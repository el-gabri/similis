# -*- coding: utf-8 -*-
"""Gera fixtures golden (normalizer text_canon + ranker output).

Rode com o código ANTIGO para capturar o comportamento de referência;
os testes de regressão comparam o código novo contra estes JSONs.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.abspath(_ROOT))

from parts.config_loader import AttributeRule, SubcategoryConfig, compute_config_hash
from parts.normalizer import normalize_dataframe
from parts.ranker import recommend

HERE = os.path.dirname(os.path.abspath(__file__))

NAMES = [
    "Fralda Pampers Confort Sec XG 58 Unidades",
    "Fralda Huggies Tripla Protecao G Leve 44 Pague 40",
    "Fralda Geriatrica Bigfral Plus G 8 Unidades",
    "Fralda MamyPoko Toque Suave M 6x22",
    "Leite em Po Ninho Integral Instantaneo 400g",
    "Leite em Po Desnatado Molico 280g",
    "Composto Lacteo Bem Bom Sabor Leite 700g",
    "Leite em Po Ninho Zero Lactose 380g",
    "Formula Infantil Aptamil Premium 2 800g",
    "Formula Infantil Nan Comfor 1 400g",
    "Formula Infantil Neocate LCP 400g",
    "Mucilon Arroz e Aveia 350g",
    "Sabonete Dove Original 90g",
    "Sabonete Liquido Protex Nutri Protect 250ml",
    "Sabonete Intimo Dermacyd Breeze 200ml",
    "Papel Higienico Neve Folha Tripla Leve 12 Pague 11 30m",
    "Papel Higienico Personal Folha Dupla 12 Rolos 60m",
    "Lenco Umedecido Huggies One Done 48 Unidades",
    "Lenco de Papel Kleenex Box 50 Folhas",
    "Papinha Nestle Frango com Legumes 170g",
    "Papinha Nestle Banana e Maca 120g",
    "Kit Viagem Necessaire Batiste 4 Pecas",
    "Kit Viagem 3 Frascos Plasutil",
    "Creme para Assaduras Bepantol Baby 60g",
    "Creme para Assaduras Tena Adulto 90g",
    "Shampoo Johnsons Baby Cabelos Claros 200ml",
    "Absorvente Always Noturno com Abas Leve 32 Pague 28",
    "Papel Higienico Compacto 4 Rolos 20m x 10cm",
    "Agua Oxigenada 10 Volumes 100ml",
    "Fralda Pampers Premium Care RN 20 Unidades",
]


def build_df():
    n = len(NAMES)
    return pd.DataFrame(
        {
            "EAN": [str(7890000000000 + i) for i in range(n)],
            "PRODUCT_NAME": NAMES,
            "product_description": ["Descricao do produto " + str(i % 5) for i in range(n)],
            "brandName": ["Marca" + str(i % 4) for i in range(n)],
            "quantity": ["" for _ in range(n)],
            "quantityUnit": ["" for _ in range(n)],
            "sizeClassification": [""] * 3 + ["M"] + [""] * (n - 4),
        }
    )


def make_config(quantity_kind="count", bounds=None, cpm=1, min_score=0.0,
                hard=("size_norm", "audience"), soft=(("quantity_norm", 1.15),),
                text=("brandName", "tipo_leite", "tipo_folha", "metragem_norm",
                      "forma_sabonete", "tipo_sabonete", "tipo_papinha", "tipo_lenco",
                      "estagio", "tipo_formula", "categoria_produto", "lactose",
                      "base_leite", "tipo_kit", "product_description")):
    rules = [AttributeRule(a, "hard_filter") for a in hard]
    rules += [AttributeRule(a, "soft_boost", 1.0, b) for a, b in soft]
    rules += [AttributeRule(a, "text_only") for a in text]
    cfg = SubcategoryConfig(
        subcategoria="fixture", subcategory_name="Fixture", category_name="Fixture Cat",
        rules=rules, top_k=10, min_score=min_score,
        quantity_ratio_bounds=bounds, quantity_kind=quantity_kind,
        candidate_pool_multiplier=cpm,
    )
    cfg.config_hash = compute_config_hash(cfg)
    return cfg


def main():
    df = build_df()

    # --- Normalizer fixture -------------------------------------------------
    cfg = make_config()
    norm = normalize_dataframe(df, cfg)
    synth_cols = [
        "quantity_norm", "size_norm", "metragem_norm", "audience", "tipo_leite",
        "base_leite", "lactose", "estagio", "tipo_formula", "categoria_produto",
        "forma_sabonete", "tipo_sabonete", "tipo_kit", "tipo_papinha",
        "tipo_lenco", "tipo_folha", "text_canon",
    ]
    normalizer_fx = {
        "names": NAMES,
        "columns": {c: norm[c].fillna("").astype(str).tolist() for c in synth_cols},
        "config_hash": cfg.config_hash,
    }
    with open(os.path.join(HERE, "normalizer_golden.json"), "w", encoding="utf-8") as f:
        json.dump(normalizer_fx, f, ensure_ascii=False, indent=1)

    # --- Ranker fixtures ----------------------------------------------------
    rng = np.random.RandomState(42)
    emb = rng.randn(len(df), 16).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    # ties deliberados: duplica embedding de 3 pares
    emb[5] = emb[4]
    emb[16] = emb[15]
    emb[29] = emb[0]

    scenarios = {
        "hard_soft": make_config(min_score=0.0),
        "bounds": make_config(bounds=(0.5, 2.0), min_score=0.0),
        "bounds_cpm": make_config(bounds=(0.5, 2.0), cpm=3, min_score=0.0),
        "min_score": make_config(min_score=0.3),
        "no_hard": make_config(hard=(), min_score=0.0),
    }
    ranker_fx = {}
    for name, c in scenarios.items():
        recs = recommend(norm, emb, c, quantity_ratio_bounds=c.quantity_ratio_bounds)
        ranker_fx[name] = {
            r["ean_origem"]: [
                {"ean": s["ean"], "relevance": s["relevance"], "rank": s["rank"]}
                for s in r["sugestoes"]
            ]
            for r in recs.to_dict("records")
        }
    with open(os.path.join(HERE, "ranker_golden.json"), "w", encoding="utf-8") as f:
        json.dump(ranker_fx, f, ensure_ascii=False, indent=1)

    print("Fixtures geradas:")
    print("  normalizer_golden.json:", len(NAMES), "produtos")
    for k, v in ranker_fx.items():
        n_sug = sum(len(s) for s in v.values())
        print(f"  ranker_golden[{k}]: {n_sug} pares")


if __name__ == "__main__":
    main()
