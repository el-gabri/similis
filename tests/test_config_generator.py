import os
import tempfile
import unittest

import yaml

from parts.config_generator import build_infos_entry_from_template
from parts.config_loader import ConfigLoader


class _SparkWithoutConfigTable:
    def table(self, _name):
        raise RuntimeError("config table unavailable")


class TestConfigGenerator(unittest.TestCase):
    def test_formula_template_uses_safety_hard_filters(self):
        entry = build_infos_entry_from_template("formula_infantil", "Fórmula Infantil")

        self.assertEqual(entry["template"], "formula_infantil")
        self.assertEqual(entry["quantity_kind"], "mass")
        # cpm=1 (default) é OMITIDO da entrada gerada — não polui YAML/hash
        self.assertNotIn("candidate_pool_multiplier", entry)
        self.assertEqual(
            entry["config_overrides"]["estagio"]["attribute_type"],
            "hard_filter",
        )
        self.assertEqual(
            entry["config_overrides"]["tipo_formula"]["attribute_type"],
            "hard_filter",
        )

    def test_template_entry_derives_category_name_from_slug(self):
        # Slug real (subcategoria__categoria): deriva subcategory_name e
        # category_name do inventário em constants.SUBCATEGORIES.
        entry = build_infos_entry_from_template("formula_infantil__alimentacao_infantil")

        self.assertEqual(entry["subcategory_name"], "Fórmula Infantil")
        self.assertEqual(entry["category_name"], "Alimentação Infantil")
        self.assertEqual(entry["template"], "formula_infantil")

    def test_config_loader_generates_known_subcategory_when_yaml_missing(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump({"list_ids": {}}, f)
            path = f.name
        try:
            loader = ConfigLoader(_SparkWithoutConfigTable(), path)
            cfg = loader.get("fraldas__troca_de_fralda")
        finally:
            os.unlink(path)

        self.assertTrue(cfg.source.startswith("generated:"))
        self.assertEqual(cfg.subcategory_name, "Fraldas")
        self.assertEqual(cfg.category_name, "Troca de Fralda")
        self.assertEqual(cfg.candidate_pool_multiplier, 1)
        hard_attrs = {r.attribute for r in cfg.hard_filter_rules}
        self.assertIn("size_norm", hard_attrs)
        self.assertIn("audience", hard_attrs)


if __name__ == "__main__":
    unittest.main()
