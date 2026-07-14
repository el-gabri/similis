import os
import tempfile
import unittest

import yaml

from parts.config_loader import (
    build_config_from_infos,
    compute_config_hash,
)
from parts.constants import nested_subcategoria


class TestConfigLoader(unittest.TestCase):
    def test_build_from_infos_with_overrides(self):
        entry = {
            "list_columns": ["PUBLICO", "TAMANHO", "MARCA_FABRICANTE"],
            "config_overrides": {
                "MARCA_FABRICANTE": {
                    "attribute_type": "hard_filter",
                    "weight": 1.0,
                    "boost_factor": 1.0,
                },
            },
            "top_k": 15,
            "min_score": 0.8,
        }
        cfg = build_config_from_infos("fraldas", entry)
        marca = next(r for r in cfg.rules if r.attribute == "MARCA_FABRICANTE")
        self.assertEqual(marca.attribute_type, "hard_filter")
        self.assertEqual(cfg.top_k, 15)
        self.assertEqual(cfg.min_score, 0.8)

    def test_config_hash_deterministic(self):
        entry = {"list_columns": ["LINHA", "TIPO"]}
        cfg1 = build_config_from_infos("x", entry)
        cfg2 = build_config_from_infos("x", entry)
        cfg1.config_hash = compute_config_hash(cfg1)
        cfg2.config_hash = compute_config_hash(cfg2)
        self.assertEqual(cfg1.config_hash, cfg2.config_hash)

    def test_nested_subcategoria_legacy_slugs(self):
        # Caso comum: slug simples do subcategory_name.
        self.assertEqual(nested_subcategoria("Fraldas"), "fraldas")
        self.assertEqual(nested_subcategoria("Lenços Umedecidos"), "lencos_umedecidos")
        # Exceção abreviada exigida pelo downstream.
        self.assertEqual(nested_subcategoria("Creme para Assaduras"), "creme_assaduras")
        # Exceções que mantêm hífen/vírgula (convenção legada).
        self.assertEqual(nested_subcategoria("Roll-on"), "roll-on")
        self.assertEqual(nested_subcategoria("Pós-Barba"), "pos-barba")
        self.assertEqual(nested_subcategoria("Cama, Mesa e Banho"), "cama,_mesa_e_banho")
        self.assertEqual(
            nested_subcategoria("Bombinha Tira-Leite"), "bombinha_tira-leite"
        )

    def test_category_name_read_from_entry_and_out_of_hash(self):
        base = {"list_columns": ["LINHA", "TIPO"]}
        entry_a = {**base, "category_name": "Absorvente Diurno"}
        entry_b = {**base, "category_name": "Absorvente Noturno"}
        cfg_a = build_config_from_infos("absorvente_com_abas__x", entry_a)
        cfg_b = build_config_from_infos("absorvente_com_abas__x", entry_b)
        self.assertEqual(cfg_a.category_name, "Absorvente Diurno")
        self.assertEqual(cfg_b.category_name, "Absorvente Noturno")
        # category_name descreve o universo, não o ruleset: fora do hash.
        self.assertEqual(cfg_a.config_hash, cfg_b.config_hash)

    def test_fallback_yaml_structure(self):
        infos = {
            "list_ids": {
                "formulas": {
                    "list_columns": ["PUBLICO", "LINHA"],
                    "top_k": 20,
                }
            }
        }
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.dump(infos, f)
            path = f.name
        try:
            cfg = build_config_from_infos("formulas", infos["list_ids"]["formulas"])
            self.assertEqual(len(cfg.rules), 2)
            self.assertTrue(all(r.attribute_type == "text_only" for r in cfg.rules))
            self.assertTrue(all(r.weight == 1.0 for r in cfg.rules))
            self.assertTrue(all(r.boost_factor == 1.0 for r in cfg.rules))
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
