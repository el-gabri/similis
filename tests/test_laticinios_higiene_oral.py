# -*- coding: utf-8 -*-
"""Templates de laticínios (lactose) e higiene oral (fluor) — fixes do G1.

Motivação (judge sobre a baseline): 674× "sem-lactose vs com lactose" em
laticínios; 254× "sem flúor vs com flúor" em cremes dentais.
"""
import unittest

import pandas as pd

from parts.config_generator import build_infos_entry_from_template
from parts.subcategory_policy import choose_template
from parts.synthetics import REGISTRY


class TestFluor(unittest.TestCase):
    def test_declarado_no_nome(self):
        casos = {
            "Gel Dental Infantil Sem Flúor Morango Boni Natural 100g": "sem_fluor",
            "Creme Dental Babysoft Zero Fluor 50g": "sem_fluor",
            "Gel Dental Fluoride Free Kids 60g": "sem_fluor",
            "Creme Dental Colgate Tripla Ação 90g": "com_fluor",
            "Gel Dental Infantil Tandy Uva 50g": "com_fluor",
            "Creme Dental Sensodyne Rápido Alívio 90g": "com_fluor",
        }
        df = pd.DataFrame({"PRODUCT_NAME": list(casos)})
        got = REGISTRY["fluor"].compute(df, None).tolist()
        for (nome, esperado), g in zip(casos.items(), got):
            self.assertEqual(g, esperado, f"{nome!r}: esperado {esperado!r}, veio {g!r}")


class TestLactoseEmLaticinios(unittest.TestCase):
    def test_sintetico_lactose_ja_cobre_laticinios(self):
        casos = {
            "Leite UHT Integral Piracanjuba 1L": "com_lactose",
            "Leite Semidesnatado Zero Lactose Piracanjuba 1L": "sem_lactose",
            "Iogurte Natural Desnatado Nestlé 160g": "com_lactose",
            "Iogurte Zero Lactose Morango Batavo 850g": "sem_lactose",
            "Leite Fermentado Yakult 480g": "com_lactose",
        }
        df = pd.DataFrame({"PRODUCT_NAME": list(casos)})
        got = REGISTRY["lactose"].compute(df, None).tolist()
        for (nome, esperado), g in zip(casos.items(), got):
            self.assertEqual(g, esperado, f"{nome!r}: esperado {esperado!r}, veio {g!r}")


class TestRoteamentoDosTemplates(unittest.TestCase):
    def test_laticinios(self):
        for slug in ("leites__bebidas", "leite_fermentado__bebidas", "iogurte_diversos__bebidas"):
            self.assertEqual(choose_template(slug).name, "laticinios", slug)

    def test_leite_em_po_continua_no_template_proprio(self):
        self.assertEqual(
            choose_template("leite_em_po__alimentacao_infantil", "Leite em Pó").name,
            "leite_em_po",
        )

    def test_higiene_oral(self):
        for slug in (
            "creme_e_gel_dental__higiene_oral",
            "creme_e_gel_dental_infantil__higiene_bucal",
        ):
            self.assertEqual(choose_template(slug).name, "higiene_oral", slug)

    def test_escova_e_fio_dental_ficam_no_higiene_generico(self):
        # flúor não se aplica a escova/fio — não devem cair no template novo
        for slug, nome in (
            ("escova_dental__higiene_oral", "Escova Dental"),
            ("fio_e_fita_dental__higiene_oral", "Fio e Fita Dental"),
        ):
            self.assertNotEqual(choose_template(slug, nome).name, "higiene_oral", slug)

    def test_config_gerada(self):
        lat = build_infos_entry_from_template("leites__bebidas", "Leites", "Bebidas")
        self.assertEqual(lat["template"], "laticinios")
        self.assertEqual(lat["quantity_kind"], "mass")
        self.assertEqual(lat["config_overrides"]["lactose"]["attribute_type"], "hard_filter")

        oral = build_infos_entry_from_template(
            "creme_e_gel_dental_infantil__higiene_bucal",
            "Creme e Gel Dental Infantil",
            "Higiene Bucal",
        )
        self.assertEqual(oral["template"], "higiene_oral")
        self.assertEqual(oral["quantity_kind"], "mass")
        self.assertEqual(oral["config_overrides"]["fluor"]["attribute_type"], "hard_filter")


if __name__ == "__main__":
    unittest.main()
