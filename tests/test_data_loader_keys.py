# -*- coding: utf-8 -*-
"""Derivação das keys do skus_metadata a partir da config (sem Spark)."""
import unittest

from parts.config_loader import AttributeRule, SubcategoryConfig
from parts.data_loader import _required_metadata_keys


def _cfg(attrs):
    return SubcategoryConfig(
        subcategoria="t",
        rules=[AttributeRule(a, "text_only") for a in attrs],
    )


class TestRequiredMetadataKeys(unittest.TestCase):
    def test_synthetics_expand_to_their_source_keys(self):
        keys = _required_metadata_keys(_cfg(["quantity_norm", "size_norm", "brandName"]))
        self.assertIn("quantity", keys)
        self.assertIn("quantityUnit", keys)
        self.assertIn("sizeClassification", keys)
        self.assertIn("diaperSize", keys)
        self.assertIn("brandName", keys)
        # sintéticos em si nunca são keys do metadata
        self.assertNotIn("quantity_norm", keys)
        self.assertNotIn("size_norm", keys)

    def test_product_description_never_pivoted(self):
        # Regressão: product_description vem do datasheet base (skus.description);
        # pivotá-la do skus_metadata duplicava a coluna no join e quebrava o
        # normalizer ('DataFrame' object has no attribute 'map').
        keys = _required_metadata_keys(_cfg(["product_description", "brandName"]))
        self.assertNotIn("product_description", keys)
        self.assertEqual(keys, ["brandName"])

    def test_name_only_synthetics_need_no_keys(self):
        keys = _required_metadata_keys(_cfg(["audience", "tipo_leite", "tipo_folha"]))
        self.assertEqual(keys, [])


if __name__ == "__main__":
    unittest.main()
