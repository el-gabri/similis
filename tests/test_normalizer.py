import unittest

from parts.config_loader import AttributeRule, SubcategoryConfig
from parts.normalizer import (
    _normalize_diaper_size,
    build_canonical_text,
    clean_text,
    convert_unit,
    normalize_dataframe,
)


class TestNormalizer(unittest.TestCase):
    def test_clean_text_idempotent(self):
        self.assertEqual(clean_text("  Áçúcar Refinado  "), "ACUCAR REFINADO")

    def test_convert_unit_kg_to_g(self):
        self.assertEqual(convert_unit("1,5 kg"), "1500 g")

    def test_convert_unit_invalid(self):
        self.assertEqual(convert_unit("xyz"), "not available")

    def test_hard_filter_tokens_removed_from_canonical(self):
        config = SubcategoryConfig(
            subcategoria="fraldas",
            rules=[
                AttributeRule("MARCA_FABRICANTE", "hard_filter", 1.0, 1.0),
                AttributeRule("LINHA", "soft_boost", 0.3, 1.1),
            ],
        )
        row = {
            "PRODUCT_NAME_CLEAN": "FRALDA DESCARTAVEL",
            "MARCA_FABRICANTE": "PAMPERS",
            "LINHA": "CONFORT",
        }
        text = build_canonical_text(row, config, list(row.keys()) + ["PRODUCT_NAME"])
        self.assertNotIn("PAMPERS", text)
        self.assertIn("CONFORT", text)

    def test_normalize_dataframe_adds_text_canon(self):
        config = SubcategoryConfig(
            subcategoria="test",
            rules=[AttributeRule("TIPO", "text_only", 0.5, 1.0)],
        )
        import pandas as pd

        df = pd.DataFrame(
            {
                "ean": ["1", "2"],
                "product_name": ["Produto A", "Produto B"],
                "TIPO": ["X", "Y"],
            }
        )
        out = normalize_dataframe(df, config)
        self.assertIn("text_canon", out.columns)
        self.assertIn("EAN", out.columns)


class TestDiaperSize(unittest.TestCase):
    def test_canonical_letters(self):
        self.assertEqual(_normalize_diaper_size("G"), "G")
        self.assertEqual(_normalize_diaper_size("M"), "M")
        self.assertEqual(_normalize_diaper_size("P"), "P")
        self.assertEqual(_normalize_diaper_size("XG"), "XG")
        self.assertEqual(_normalize_diaper_size("XXG"), "XXG")
        self.assertEqual(_normalize_diaper_size("XXXG"), "XXXG")

    def test_brackets_and_lowercase(self):
        # Vem assim do skus_metadata Farma: "[G]", "[XG]", etc.
        self.assertEqual(_normalize_diaper_size("[G]"), "G")
        self.assertEqual(_normalize_diaper_size("[XG]"), "XG")
        self.assertEqual(_normalize_diaper_size("xxg"), "XXG")

    def test_synonyms(self):
        self.assertEqual(_normalize_diaper_size("EG"), "XG")
        self.assertEqual(_normalize_diaper_size("Extra grande"), "XG")
        self.assertEqual(_normalize_diaper_size("Extra grande (xg)"), "XG")
        self.assertEqual(_normalize_diaper_size("Recém nascido"), "RN")

    def test_extract_from_product_name(self):
        self.assertEqual(
            _normalize_diaper_size("Fralda Infantil Pampers Confort Sec G 28 Unidades"),
            "G",
        )
        self.assertEqual(
            _normalize_diaper_size("Fralda Diguinho Plus Econômica XXG 18 Un"),
            "XXG",
        )

    def test_unknown_returns_empty(self):
        self.assertEqual(_normalize_diaper_size(""), "")
        self.assertEqual(_normalize_diaper_size("sem tamanho aqui"), "")
        self.assertEqual(_normalize_diaper_size(None), "")  # type: ignore[arg-type]

    def test_size_norm_column_is_added_when_inputs_exist(self):
        import pandas as pd

        config = SubcategoryConfig(
            subcategoria="fraldas",
            rules=[AttributeRule("size_norm", "hard_filter", 1.0, 1.0)],
        )
        df = pd.DataFrame(
            {
                "EAN": ["1", "2", "3"],
                "PRODUCT_NAME": [
                    "Fralda Pampers G 28un",
                    "Fralda Diguinho M 16un",
                    "Fralda Wipex XXG",
                ],
                # Misturando as 3 fontes para garantir o fallback.
                "sizeClassification": ["[G]", "", ""],
                "diaperSize": ["", "M", ""],
                "brandSize": ["", "", ""],
            }
        )
        out = normalize_dataframe(df, config)
        self.assertIn("size_norm", out.columns)
        self.assertEqual(out.set_index("EAN")["size_norm"].to_dict(), {"1": "G", "2": "M", "3": "XXG"})


if __name__ == "__main__":
    unittest.main()
