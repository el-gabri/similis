# -*- coding: utf-8 -*-
"""Regressão contra golden fixtures.

As fixtures (tests/fixtures/*.json) capturam o comportamento de referência do
pipeline normalize -> recommend. Qualquer refactor que NÃO pretenda mudar
resultados deve manter estes testes verdes byte a byte. Mudança INTENCIONAL de
comportamento => regenerar as fixtures (tests/fixtures/generate_fixtures.py) na
MESMA revisão, com bump de MODEL_VERSION e diff revisado no PR.
"""
import json
import os
import sys
import unittest

import numpy as np

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
sys.path.insert(0, _FIXTURES)

from generate_fixtures import NAMES, build_df, make_config  # noqa: E402

from parts.normalizer import normalize_dataframe  # noqa: E402
from parts.ranker import recommend  # noqa: E402


def _load(name):
    with open(os.path.join(_FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def _make_embeddings(n, dim=16):
    rng = np.random.RandomState(42)
    emb = rng.randn(n, dim).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    # ties deliberados (espelha generate_fixtures)
    emb[5] = emb[4]
    emb[16] = emb[15]
    emb[29] = emb[0]
    return emb


class TestNormalizerGolden(unittest.TestCase):
    def test_synthetics_and_text_canon_match_golden(self):
        golden = _load("normalizer_golden.json")
        self.assertEqual(golden["names"], NAMES, "fixture desatualizada vs NAMES")

        cfg = make_config()
        norm = normalize_dataframe(build_df(), cfg)
        self.assertEqual(cfg.config_hash, golden["config_hash"])
        for col, expected in golden["columns"].items():
            got = norm[col].fillna("").astype(str).tolist()
            self.assertEqual(got, expected, f"coluna {col} divergiu do golden")


class TestRankerGolden(unittest.TestCase):
    def test_all_scenarios_match_golden(self):
        golden = _load("ranker_golden.json")
        norm = normalize_dataframe(build_df(), make_config())
        emb = _make_embeddings(len(NAMES))

        scenarios = {
            "hard_soft": make_config(min_score=0.0),
            "bounds": make_config(bounds=(0.5, 2.0), min_score=0.0),
            "bounds_cpm": make_config(bounds=(0.5, 2.0), cpm=3, min_score=0.0),
            "min_score": make_config(min_score=0.3),
            "no_hard": make_config(hard=(), min_score=0.0),
        }
        for name, cfg in scenarios.items():
            recs = recommend(
                norm, emb, cfg, quantity_ratio_bounds=cfg.quantity_ratio_bounds
            )
            got = {
                r["ean_origem"]: [
                    {"ean": s["ean"], "relevance": s["relevance"], "rank": s["rank"]}
                    for s in r["sugestoes"]
                ]
                for r in recs.to_dict("records")
            }
            self.assertEqual(got, golden[name], f"cenário {name} divergiu do golden")


if __name__ == "__main__":
    unittest.main()
