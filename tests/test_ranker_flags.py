# -*- coding: utf-8 -*-
"""Flags novas do ranker (default preserva comportamento histórico)."""
import unittest

import numpy as np
import pandas as pd

from parts.config_loader import AttributeRule, SubcategoryConfig
from parts.ranker import recommend


def _embs():
    # 4 vetores: 0~1 muito próximos; 2 próximo; 3 distante.
    base = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    close = np.array([0.99, 0.14, 0.0, 0.0], dtype=np.float32)
    mid = np.array([0.7, 0.7, 0.14, 0.0], dtype=np.float32)
    far = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32)
    embs = np.stack([base, close, mid, far])
    return embs / np.linalg.norm(embs, axis=1, keepdims=True)


def _df():
    return pd.DataFrame(
        {
            "EAN": ["1", "2", "3", "4"],
            "product_id": ["p1", "p1", "p3", "p4"],  # 1 e 2 = mesmo produto
            "TIPO": ["A", "A", "A", "A"],
        }
    )


def _config(**kwargs):
    cfg = SubcategoryConfig(
        subcategoria="t",
        rules=[AttributeRule("TIPO", "soft_boost", 1.0, 1.2)],
        top_k=5,
        min_score=kwargs.pop("min_score", 0.0),
    )
    for k, v in kwargs.items():
        setattr(cfg, k, v)
    return cfg


class TestSuppressSameProduct(unittest.TestCase):
    def test_default_keeps_same_product(self):
        recs = recommend(_df(), _embs(), _config())
        sugs_1 = recs[recs["ean_origem"] == "1"]["sugestoes"].iloc[0]
        self.assertIn("2", [s["ean"] for s in sugs_1])

    def test_flag_suppresses_same_product(self):
        recs = recommend(_df(), _embs(), _config(suppress_same_product=True))
        sugs_1 = recs[recs["ean_origem"] == "1"]["sugestoes"].iloc[0]
        eans = [s["ean"] for s in sugs_1]
        self.assertNotIn("2", eans)  # mesmo product_id da origem
        self.assertIn("3", eans)


class TestMinScoreBasis(unittest.TestCase):
    def test_boosted_default_boost_can_save_candidate(self):
        # sim(1,3) < min_score, mas boost 1.2 salva (comportamento histórico).
        embs = _embs()
        sim_13 = float(embs[0] @ embs[2])
        min_score = sim_13 + 0.01  # acima da sim pura, abaixo do pós-boost
        self.assertLess(min_score, sim_13 * 1.2)

        recs = recommend(_df(), embs, _config(min_score=min_score))
        sugs_1 = recs[recs["ean_origem"] == "1"]["sugestoes"].iloc[0]
        self.assertIn("3", [s["ean"] for s in sugs_1])

    def test_raw_similarity_basis_cuts_before_boost(self):
        embs = _embs()
        sim_13 = float(embs[0] @ embs[2])
        min_score = sim_13 + 0.01

        recs = recommend(
            _df(), embs, _config(min_score=min_score, min_score_basis="raw_similarity")
        )
        sugs_1 = recs[recs["ean_origem"] == "1"]["sugestoes"].iloc[0]
        self.assertNotIn("3", [s["ean"] for s in sugs_1])


if __name__ == "__main__":
    unittest.main()
