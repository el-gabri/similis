# -*- coding: utf-8 -*-
"""E2E Spark-free: normalize -> recommend -> prepare_recommendations_output.

Garante que o contrato das saídas (colunas e chaves do JSON de sugestões)
não muda — é consumido por downstream em produção.
"""
import json
import unittest

import numpy as np
import pandas as pd

from parts.config_loader import AttributeRule, SubcategoryConfig, compute_config_hash
from parts.normalizer import normalize_dataframe
from parts.ranker import recommend
from parts.writer import (
    FLAT_COLUMN_NAMES,
    RECOMMENDATIONS_COLUMN_NAMES,
    prepare_recommendations_output,
)

EXPECTED_NESTED_COLUMNS = (
    "ean_origem", "product_name_origem", "subcategoria", "sugestoes",
    "n_sugestoes", "model_version", "config_hash", "date",
)
EXPECTED_FLAT_COLUMNS = (
    "ean_origem", "product_name_origem", "ean_sugestao", "product_name_sugestao",
    "rank", "relevance", "n_sugestoes", "subcategoria", "categoria",
    "model_version", "config_hash", "date",
)
EXPECTED_SUGGESTION_KEYS = {"ean", "relevance", "rank", "product_name"}


class TestEndToEndPipeline(unittest.TestCase):
    def test_contract_columns_frozen(self):
        # Se este teste falhar, o schema das tabelas de produção mudou —
        # NÃO pode acontecer sem alinhamento com o downstream.
        self.assertEqual(RECOMMENDATIONS_COLUMN_NAMES, EXPECTED_NESTED_COLUMNS)
        self.assertEqual(FLAT_COLUMN_NAMES, EXPECTED_FLAT_COLUMNS)

    def test_pipeline_and_suggestion_json_contract(self):
        names = [
            "Fralda Marca A Tamanho G 30 Unidades",
            "Fralda Marca B Tamanho G 32 Unidades",
            "Fralda Marca C Tamanho G 60 Unidades",
        ]
        df = pd.DataFrame(
            {
                "EAN": ["100", "200", "300"],
                "PRODUCT_NAME": names,
                "product_description": [""] * 3,
                "brandName": ["A", "B", "C"],
            }
        )
        cfg = SubcategoryConfig(
            subcategoria="fraldas__troca_de_fralda",
            subcategory_name="Fraldas",
            category_name="Troca de Fralda",
            rules=[
                AttributeRule("size_norm", "hard_filter"),
                AttributeRule("quantity_norm", "soft_boost", 1.0, 1.15),
                AttributeRule("brandName", "text_only"),
            ],
            top_k=5,
            min_score=0.0,
            quantity_ratio_bounds=(0.5, 2.0),
        )
        cfg.config_hash = compute_config_hash(cfg)

        norm = normalize_dataframe(df, cfg)
        rng = np.random.RandomState(7)
        emb = rng.randn(len(norm), 8).astype(np.float32)
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)

        recs = recommend(norm, emb, cfg, quantity_ratio_bounds=cfg.quantity_ratio_bounds)
        nested, flat, run_date = prepare_recommendations_output(
            recs,
            "fraldas__troca_de_fralda",
            cfg.config_hash,
            run_date="2026-07-05",
            name_by_ean=norm.set_index("EAN")["PRODUCT_NAME"].to_dict(),
            category_name=cfg.category_name,
            subcategoria_nested="fraldas",
        )

        self.assertEqual(tuple(nested.columns), EXPECTED_NESTED_COLUMNS)
        self.assertEqual(tuple(flat.columns), EXPECTED_FLAT_COLUMNS)
        self.assertEqual(nested["subcategoria"].unique().tolist(), ["fraldas"])
        self.assertEqual(flat["categoria"].unique().tolist(), ["troca_de_fralda"])

        for sugs_json in nested["sugestoes"]:
            for s in json.loads(sugs_json):
                self.assertEqual(set(s.keys()), EXPECTED_SUGGESTION_KEYS)

        # quantity filter: origem 30un não deve sugerir 60un... 60/30=2.0
        # está NO limite (lo=0.5, hi=2.0, inclusive) — mantido. 30->32 ok.
        self.assertGreater(len(flat), 0)


if __name__ == "__main__":
    unittest.main()
