# -*- coding: utf-8 -*-
"""Filtros de universo nomeados + integração com normalize_dataframe."""
import unittest

import pandas as pd

from parts.config_loader import AttributeRule, SubcategoryConfig, compute_config_hash
from parts.normalizer import normalize_dataframe
from parts.universe_filters import apply_universe_exclusions


def _df(names):
    return pd.DataFrame(
        {
            "EAN": [str(i) for i in range(len(names))],
            "PRODUCT_NAME": names,
            "product_description": [""] * len(names),
        }
    )


class TestApplyUniverseExclusions(unittest.TestCase):
    def test_nao_leite_em_po_removes_formula_and_supplement(self):
        df = _df(
            [
                "Leite em Po Ninho Integral 400g",       # fica
                "Formula Infantil Aptamil Premium 2",     # sai (fórmula)
                "Sustagen Kids Chocolate 380g",           # sai (suplemento)
                "Composto Lacteo Bem Bom 700g",           # fica (composto é legítimo)
            ]
        )
        out = apply_universe_exclusions(df, ["nao_leite_em_po"])
        self.assertEqual(
            out["PRODUCT_NAME"].tolist(),
            ["Leite em Po Ninho Integral 400g", "Composto Lacteo Bem Bom 700g"],
        )

    def test_unknown_exclusion_raises(self):
        with self.assertRaises(ValueError):
            apply_universe_exclusions(_df(["X"]), ["nao_existe"])

    def test_empty_exclusions_noop(self):
        df = _df(["Formula Infantil Nan 1"])
        out = apply_universe_exclusions(df, [])
        self.assertEqual(len(out), 1)


class TestNormalizeAppliesExclusions(unittest.TestCase):
    def _config(self, exclusions=()):
        cfg = SubcategoryConfig(
            subcategoria="leite_em_po__alimentacao_infantil",
            subcategory_name="Leite em Pó",
            rules=[AttributeRule("brandName", "text_only")],
            universe_exclusions=tuple(exclusions),
        )
        cfg.config_hash = compute_config_hash(cfg)
        return cfg

    def test_exclusion_removes_origin_and_candidate(self):
        df = _df(["Leite Ninho Integral 400g", "Formula Infantil Nan Comfor 1"])
        df["brandName"] = ["Ninho", "Nan"]
        out = normalize_dataframe(df, self._config(["nao_leite_em_po"]))
        self.assertEqual(out["PRODUCT_NAME"].tolist(), ["Leite Ninho Integral 400g"])

    def test_no_exclusion_keeps_all(self):
        df = _df(["Leite Ninho Integral 400g", "Formula Infantil Nan Comfor 1"])
        df["brandName"] = ["Ninho", "Nan"]
        out = normalize_dataframe(df, self._config())
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
