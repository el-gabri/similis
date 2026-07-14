import unittest

import numpy as np
import pandas as pd

from parts.config_loader import AttributeRule, SubcategoryConfig
from parts.ranker import recommend


class TestRanker(unittest.TestCase):
    def _make_similar_embeddings(self, n: int, dim: int = 8):
        base = np.random.randn(dim).astype(np.float32)
        base = base / np.linalg.norm(base)
        embs = []
        for i in range(n):
            noise = np.random.randn(dim).astype(np.float32) * 0.05 * i
            v = base + noise
            v = v / np.linalg.norm(v)
            embs.append(v)
        return np.stack(embs)

    def test_hard_filter_partitions(self):
        config = SubcategoryConfig(
            subcategoria="fraldas",
            rules=[
                AttributeRule("MARCA", "hard_filter", 1.0, 1.0),
            ],
            top_k=5,
            min_score=0.0,
        )
        df = pd.DataFrame(
            {
                "EAN": ["1", "2", "3", "4"],
                "MARCA": ["A", "A", "B", "B"],
            }
        )
        embs = self._make_similar_embeddings(4)
        recs = recommend(df, embs, config)
        row1 = recs[recs["ean_origem"] == "1"].iloc[0]
        suggested = [s["ean"] for s in row1["sugestoes"]]
        self.assertIn("2", suggested)
        self.assertNotIn("3", suggested)
        self.assertNotIn("4", suggested)

    def test_origin_not_in_own_suggestions(self):
        config = SubcategoryConfig(subcategoria="t", rules=[], top_k=3, min_score=0.0)
        df = pd.DataFrame({"EAN": ["1", "2"], "MARCA": ["A", "A"]})
        embs = self._make_similar_embeddings(2)
        recs = recommend(df, embs, config)
        for _, row in recs.iterrows():
            eans = [s["ean"] for s in row["sugestoes"]]
            self.assertNotIn(row["ean_origem"], eans)

    def test_soft_boost_increases_relevance_for_matching_attribute(self):
        config = SubcategoryConfig(
            subcategoria="t",
            rules=[AttributeRule("LINHA", "soft_boost", 0.3, 2.0)],
            top_k=5,
            min_score=0.0,
        )
        df = pd.DataFrame(
            {
                "EAN": ["1", "2", "3"],
                "LINHA": ["X", "Y", "X"],
            }
        )
        embs = self._make_similar_embeddings(3)
        recs = recommend(df, embs, config)
        row1 = recs[recs["ean_origem"] == "1"].iloc[0]
        relevance_by_ean = {s["ean"]: s["relevance"] for s in row1["sugestoes"]}
        if "2" in relevance_by_ean and "3" in relevance_by_ean:
            self.assertGreater(relevance_by_ean["3"], relevance_by_ean["2"])

    def test_suggestions_have_relevance_and_rank_keys(self):
        config = SubcategoryConfig(
            subcategoria="t",
            rules=[],
            top_k=3,
            min_score=0.0,
        )
        df = pd.DataFrame({"EAN": ["1", "2", "3"]})
        embs = self._make_similar_embeddings(3)
        recs = recommend(df, embs, config)
        for _, row in recs.iterrows():
            for sug in row["sugestoes"]:
                self.assertIn("ean", sug)
                self.assertIn("relevance", sug)
                self.assertIn("rank", sug)
                self.assertNotIn("score", sug)

    def test_suggestions_sorted_by_relevance_desc(self):
        config = SubcategoryConfig(
            subcategoria="t",
            rules=[],
            top_k=10,
            min_score=0.0,
        )
        df = pd.DataFrame({"EAN": [str(i) for i in range(5)]})
        embs = self._make_similar_embeddings(5)
        recs = recommend(df, embs, config)
        for _, row in recs.iterrows():
            relevances = [s["relevance"] for s in row["sugestoes"]]
            self.assertEqual(relevances, sorted(relevances, reverse=True))
            ranks = [s["rank"] for s in row["sugestoes"]]
            self.assertEqual(ranks, list(range(1, len(ranks) + 1)))

    def test_relevance_normalized_to_unit_interval(self):
        """Com normalize_relevance=True (default), todas as relevâncias estão em [0, 1]
        e o melhor par tem relevância == 1.0."""
        config = SubcategoryConfig(
            subcategoria="t",
            rules=[AttributeRule("MARCA", "soft_boost", 1.0, 1.5)],
            top_k=10,
            min_score=0.0,
        )
        df = pd.DataFrame(
            {
                "EAN": ["1", "2", "3", "4"],
                "MARCA": ["A", "A", "A", "B"],
            }
        )
        embs = self._make_similar_embeddings(4)
        recs = recommend(df, embs, config)
        all_rel = [s["relevance"] for _, row in recs.iterrows() for s in row["sugestoes"]]
        self.assertTrue(all_rel, "esperava ao menos uma sugestão")
        for r in all_rel:
            self.assertGreaterEqual(r, 0.0)
            self.assertLessEqual(r, 1.0)
        self.assertAlmostEqual(max(all_rel), 1.0, places=6)

    def test_normalize_relevance_preserves_order(self):
        """Normalizar não pode reordenar o ranking."""
        config = SubcategoryConfig(
            subcategoria="t",
            rules=[AttributeRule("LINHA", "soft_boost", 1.0, 1.5)],
            top_k=10,
            min_score=0.0,
        )
        df = pd.DataFrame(
            {
                "EAN": ["1", "2", "3", "4"],
                "LINHA": ["X", "X", "Y", "Y"],
            }
        )
        embs = self._make_similar_embeddings(4)
        recs_norm = recommend(df, embs, config, normalize_relevance=True)
        recs_raw = recommend(df, embs, config, normalize_relevance=False)
        for (_, rn), (_, rr) in zip(recs_norm.iterrows(), recs_raw.iterrows()):
            eans_norm = [s["ean"] for s in rn["sugestoes"]]
            eans_raw = [s["ean"] for s in rr["sugestoes"]]
            self.assertEqual(eans_norm, eans_raw)

    def test_normalize_relevance_can_be_disabled(self):
        """Com normalize_relevance=False o boost pode levar relevância acima de 1.0."""
        config = SubcategoryConfig(
            subcategoria="t",
            rules=[AttributeRule("LINHA", "soft_boost", 1.0, 1.5)],
            top_k=10,
            min_score=0.0,
        )
        df = pd.DataFrame({"EAN": ["1", "2"], "LINHA": ["X", "X"]})
        embs = np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
        recs = recommend(df, embs, config, normalize_relevance=False)
        all_rel = [s["relevance"] for _, row in recs.iterrows() for s in row["sugestoes"]]
        self.assertTrue(any(r > 1.0 for r in all_rel))

    def test_min_score_filters_weak(self):
        config = SubcategoryConfig(
            subcategoria="t",
            rules=[],
            top_k=10,
            min_score=0.99,
        )
        df = pd.DataFrame({"EAN": ["1", "2"]})
        embs = np.array([[1, 0], [0, 1]], dtype=np.float32)
        recs = recommend(df, embs, config)
        row1 = recs[recs["ean_origem"] == "1"].iloc[0]
        self.assertEqual(row1["sugestoes"], [])

    def test_candidate_pool_multiplier_recovers_after_quantity_filter(self):
        config = SubcategoryConfig(
            subcategoria="t",
            rules=[],
            top_k=1,
            min_score=0.0,
            quantity_ratio_bounds=(0.5, 2.0),
            candidate_pool_multiplier=3,
        )
        df = pd.DataFrame(
            {
                "EAN": ["1", "2", "3"],
                "quantity_norm": ["100 un", "1000 un", "100 un"],
            }
        )
        embs = np.array(
            [
                [1.0, 0.0],
                [0.99, 0.01],  # vizinho mais próximo, mas descartado por quantidade
                [0.90, 0.10],  # candidato válido que só aparece com pool maior
            ],
            dtype=np.float32,
        )

        recs = recommend(
            df,
            embs,
            config,
            quantity_ratio_bounds=config.quantity_ratio_bounds,
        )
        row1 = recs[recs["ean_origem"] == "1"].iloc[0]
        self.assertEqual([s["ean"] for s in row1["sugestoes"]], ["3"])


if __name__ == "__main__":
    unittest.main()
