# -*- coding: utf-8 -*-
"""Precedência do merge de config: Delta > infos.yaml > template."""
import os
import tempfile
import unittest

import yaml

from parts.config_loader import ConfigLoader, build_config_from_infos


class _FakeColumn:
    def __init__(self, values_by_row):
        self.values_by_row = values_by_row


class _FakeRow(dict):
    def asDict(self):
        return dict(self)


class _FakeSparkDF:
    def __init__(self, rows):
        self._rows = rows

    def __getitem__(self, col):
        return col

    def where(self, cond):
        # cond é ignorada: o fake devolve todas as linhas (os testes montam
        # só linhas da subcategoria consultada, todas active=True).
        return self

    def collect(self):
        return [_FakeRow(r) for r in self._rows]


class _FakeSpark:
    def __init__(self, rows=None, fail=False):
        self._rows = rows or []
        self._fail = fail

    def table(self, name):
        if self._fail:
            raise RuntimeError("tabela indisponível")
        return _FakeSparkDF(self._rows)


def _write_infos(payload) -> str:
    f = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.safe_dump(payload, f, allow_unicode=True)
    f.close()
    return f.name


class TestConfigMerge(unittest.TestCase):
    def tearDown(self):
        if getattr(self, "_infos_path", None) and os.path.exists(self._infos_path):
            os.unlink(self._infos_path)

    def _loader(self, spark, infos):
        self._infos_path = _write_infos(infos)
        return ConfigLoader(spark, self._infos_path)

    def test_delta_rules_win_yaml_fills_missing_scalars(self):
        # Delta legado: tem regras mas NÃO tem quantity_kind/bounds/cpm.
        delta_rows = [
            {
                "subcategoria": "fraldas__troca_de_fralda",
                "subcategory_name": "Fraldas",
                "attribute": "size_norm",
                "attribute_type": "hard_filter",
                "weight": 1.0,
                "boost_factor": 1.0,
                "top_k": 30,
                "min_score": 0.6,
                "active": True,
            }
        ]
        infos = {
            "list_ids": {
                "fraldas__troca_de_fralda": {
                    "subcategory_name": "Fraldas (YAML não deve vencer)",
                    "top_k": 99,
                    "quantity_ratio_bounds": [0.5, 2.0],
                    "quantity_kind": "mass",
                    "candidate_pool_multiplier": 3,
                    "list_columns": ["brandName"],
                }
            }
        }
        cfg = self._loader(_FakeSpark(delta_rows), infos).get("fraldas__troca_de_fralda")

        # Delta vence onde definiu:
        self.assertEqual(cfg.source, "delta")
        self.assertEqual([r.attribute for r in cfg.rules], ["size_norm"])
        self.assertEqual(cfg.top_k, 30)
        self.assertEqual(cfg.min_score, 0.6)
        self.assertEqual(cfg.subcategory_name, "Fraldas")
        # YAML completa o que o Delta legado não tem:
        self.assertEqual(cfg.quantity_ratio_bounds, (0.5, 2.0))
        self.assertEqual(cfg.quantity_kind, "mass")
        self.assertEqual(cfg.candidate_pool_multiplier, 3)
        self.assertTrue(cfg.config_hash)

    def test_yaml_when_delta_empty(self):
        infos = {
            "list_ids": {
                "talco__troca_de_fralda": {
                    "subcategory_name": "Talco",
                    "list_columns": ["brandName", "quantity_norm"],
                    "top_k": 15,
                }
            }
        }
        cfg = self._loader(_FakeSpark(fail=True), infos).get("talco__troca_de_fralda")
        self.assertEqual(cfg.source, "infos.yaml")
        self.assertEqual(cfg.top_k, 15)
        self.assertEqual(len(cfg.rules), 2)

    def test_template_when_no_delta_and_no_yaml(self):
        cfg = self._loader(_FakeSpark(fail=True), {"list_ids": {}}).get(
            "fraldas__troca_de_fralda"
        )
        self.assertTrue(cfg.source.startswith("generated:"))
        self.assertTrue(cfg.rules)

    def test_hash_computed_once_and_stable(self):
        infos_entry = {
            "subcategory_name": "Fraldas",
            "list_columns": ["size_norm", "brandName"],
            "config_overrides": {"size_norm": {"attribute_type": "hard_filter"}},
        }
        c1 = build_config_from_infos("fraldas__troca_de_fralda", infos_entry)
        c2 = build_config_from_infos("fraldas__troca_de_fralda", infos_entry)
        self.assertEqual(c1.config_hash, c2.config_hash)
        self.assertTrue(c1.config_hash)

    def test_universe_exclusions_enter_hash_only_when_set(self):
        base = {"subcategory_name": "Leite em Pó", "list_columns": ["brandName"]}
        with_excl = dict(base, universe_exclusions=["nao_leite_em_po"])
        c_base = build_config_from_infos("x", base)
        c_excl = build_config_from_infos("x", with_excl)
        self.assertNotEqual(c_base.config_hash, c_excl.config_hash)
        self.assertEqual(c_excl.universe_exclusions, ("nao_leite_em_po",))
        self.assertEqual(c_base.universe_exclusions, ())

    def test_legacy_leite_em_po_default_exclusion(self):
        # Comportamento herdado do bloco hard-coded do normalizer antigo,
        # que era gated no slug legado "leite_em_po".
        entry = {"subcategory_name": "Leite em Pó", "list_columns": ["brandName"]}
        cfg = build_config_from_infos("leite_em_po", entry)
        self.assertEqual(cfg.universe_exclusions, ("nao_leite_em_po",))

    def test_min_score_basis_default_out_of_hash(self):
        base = {"subcategory_name": "X", "list_columns": ["brandName"]}
        explicit = dict(base, min_score_basis="boosted")
        raw = dict(base, min_score_basis="raw_similarity")
        self.assertEqual(
            build_config_from_infos("x", base).config_hash,
            build_config_from_infos("x", explicit).config_hash,
        )
        self.assertNotEqual(
            build_config_from_infos("x", base).config_hash,
            build_config_from_infos("x", raw).config_hash,
        )


if __name__ == "__main__":
    unittest.main()
