# -*- coding: utf-8 -*-
"""Correções v1.7 guiadas pelo judge: fallback unit-aware do quantity_norm,
sintéticos novos (forma_bebida, faixa_etaria_bebe, tipo_bateria,
tipo_agua_terapeutica) e exclusions W4 por default de slug."""
import unittest

import pandas as pd

from parts.config_loader import (
    _DEFAULT_UNIVERSE_EXCLUSIONS,
    AttributeRule,
    SubcategoryConfig,
    build_config_from_infos,
)
from parts.constants import SUBCATEGORIES
from parts.subcategory_policy import choose_template
from parts.synthetics import REGISTRY
from parts.universe_filters import KNOWN_EXCLUSIONS, apply_universe_exclusions


def _quantity_norm(names, quantity=None, unit=None, kind="count"):
    df = pd.DataFrame({"PRODUCT_NAME": names})
    if quantity is not None:
        df["quantity"] = quantity
        df["quantityUnit"] = unit
    cfg = SubcategoryConfig(subcategoria="t", rules=[], quantity_kind=kind)
    return REGISTRY["quantity_norm"].compute(df, cfg).tolist()


class TestQuantityFallbackUnitAware(unittest.TestCase):
    def test_count_mode_respeita_quantity_unit_ml(self):
        # O caso das 53 subcategorias: nome sem token de contagem, metadata
        # em ml — antes virava "200 un", agora vira "200 ml".
        got = _quantity_norm(
            ["Colônia Infantil Suave", "Álcool Gel Antisséptico"],
            quantity=["200", "500"], unit=["ml", "ML"],
        )
        self.assertEqual(got, ["200 ml", "500 ml"])

    def test_count_mode_respeita_gramas_e_litros(self):
        got = _quantity_norm(
            ["Descolorante Profissional", "Aromatizante de Ambiente"],
            quantity=["80", "1"], unit=["g", "l"],
        )
        self.assertEqual(got, ["80 g", "1000 ml"])

    def test_count_mode_contagem_verdadeira_preservada(self):
        # unidade de contagem no metadata -> comportamento antigo ("N un")
        got = _quantity_norm(
            ["Elástico de Cabelo Sortido", "Curativo Adesivo Transparente"],
            quantity=["12", "20"], unit=["un", "unidades"],
        )
        self.assertEqual(got, ["12 un", "20 un"])

    def test_count_mode_sem_unit_mantem_un(self):
        got = _quantity_norm(["Demaquilante Bifásico"], quantity=["100"], unit=[""])
        self.assertEqual(got, ["100 un"])

    def test_nome_com_contagem_continua_prioritario(self):
        # parse_pack_size do NOME vence o metadata, como sempre
        got = _quantity_norm(
            ["Absorvente 16un Leve Mais Pague Menos"],
            quantity=["999"], unit=["ml"],
        )
        self.assertEqual(got, ["16 un"])


class TestSinteticosNovos(unittest.TestCase):
    def _run(self, attr, casos):
        df = pd.DataFrame({"PRODUCT_NAME": list(casos)})
        got = REGISTRY[attr].compute(df, None).tolist()
        for (nome, esperado), g in zip(casos.items(), got):
            self.assertEqual(g, esperado, f"{attr}: {nome!r} -> {g!r} (esperado {esperado!r})")

    def test_forma_bebida(self):
        self._run("forma_bebida", {
            "Achocolatado em Pó Nescau 370g": "po",
            "Achocolatado Solúvel Toddy 400g": "po",
            "Bebida Láctea Achocolatada Toddynho 200ml": "",
            "Café em Cápsulas Espresso 10 Cápsulas": "capsula",
            "Whey Protein em Pó Baunilha 900g": "po",
            "Barra Proteica Bold Chocolate 60g": "",
        })

    def test_faixa_etaria_bebe(self):
        self._run("faixa_etaria_bebe", {
            "Chupeta Lillo Soft Calming 0-6 Meses": "fase1",
            "Chupeta NUK Space 6-18m": "fase2",
            "Chupeta Fase 1 Ortodôntica Recém Nascido": "fase1",
            "Chupeta Fase 2 Noturna": "fase2",
            "Chupeta Avent Ultra Air": "",
        })

    def test_tipo_bateria(self):
        self._run("tipo_bateria", {
            "Pilha Alcalina AA Duracell 4 Unidades": "aa",
            "Pilha Palito AAA Panasonic 2un": "aaa",
            "Bateria 9V Alcalina Elgin": "9v",
            "Bateria de Lítio CR2032 3V": "botao",
            "Bateria para Monitor de Pressão": "",
        })

    def test_tipo_agua_terapeutica(self):
        self._run("tipo_agua_terapeutica", {
            "Água Oxigenada 10 Volumes 100ml": "oxigenada",
            "Água Boricada Farmax 100ml": "boricada",
            "Solução de Ácido Bórico 3%": "boricada",
            "Solução Antisséptica 100ml": "",
        })


class TestRoteamentoV17(unittest.TestCase):
    def test_templates_novos(self):
        self.assertEqual(
            choose_template("baterias_para_monitores__aparelhos_e_monitores").name,
            "baterias",
        )
        self.assertEqual(
            choose_template("agua_oxigenada_e_boricada__antissepticos").name,
            "agua_terapeutica",
        )

    def test_forma_bebida_no_template_alimentos(self):
        from parts.config_generator import build_infos_entry_from_template
        entry = build_infos_entry_from_template("achocolatado_pronto__bebidas")
        self.assertEqual(entry["template"], "alimentos_bebidas")
        self.assertEqual(
            entry["config_overrides"]["forma_bebida"]["attribute_type"], "hard_filter"
        )

    def test_faixa_etaria_no_template_bebe(self):
        from parts.config_generator import build_infos_entry_from_template
        entry = build_infos_entry_from_template("chupetas__acessorios_para_bebes")
        self.assertEqual(entry["template"], "bebe_cuidados")
        self.assertEqual(
            entry["config_overrides"]["faixa_etaria_bebe"]["attribute_type"],
            "hard_filter",
        )


class TestExclusionsW4(unittest.TestCase):
    def test_slugs_dos_defaults_existem_no_inventario(self):
        for slug in _DEFAULT_UNIVERSE_EXCLUSIONS:
            if slug == "leite_em_po":  # slug legado de notebook, fora do inventário
                continue
            self.assertIn(slug, SUBCATEGORIES, f"slug inexistente: {slug}")

    def test_exclusions_dos_defaults_sao_conhecidas(self):
        for exclusions in _DEFAULT_UNIVERSE_EXCLUSIONS.values():
            for e in exclusions:
                self.assertIn(e, KNOWN_EXCLUSIONS, e)

    def test_default_aplicado_e_hasheado(self):
        entry = {"subcategory_name": "Adoçante", "list_columns": ["brandName"]}
        cfg = build_config_from_infos("adocante__mercado", entry)
        self.assertEqual(cfg.universe_exclusions, ("acucar",))
        sem = build_config_from_infos("outra__qualquer", entry)
        self.assertNotEqual(cfg.config_hash, sem.config_hash)

    def test_config_explicita_vence_o_default(self):
        entry = {
            "subcategory_name": "Adoçante",
            "list_columns": ["brandName"],
            "universe_exclusions": [],
        }
        cfg = build_config_from_infos("adocante__mercado", entry)
        self.assertEqual(cfg.universe_exclusions, ())

    def test_padroes_das_exclusions(self):
        casos = {
            "acucar": (["Açúcar Refinado União 1kg"], ["Adoçante Sucralose Linea 75ml"]),
            "absorvente_externo": (
                ["Absorvente com Abas Always Noturno"],
                ["Absorvente Interno OB Médio 8un"],
            ),
            "sem_alcool": (["Cerveja Heineken 0.0% Sem Álcool"], ["Vinho Tinto Suave 750ml"]),
            "coletor_hospitalar": (["Bolsa de Colostomia 45mm"], ["Bolsa Térmica Gel Quente Frio"]),
            "medicamentoso_dermo": (["Creme Betametasona 0,5mg/g"], ["Sérum Facial Vitamina C"]),
            "pastilha_medicinal": (["Pastilha Strepsils Mel e Limão"], ["Bala Fini Dentadura"]),
            "produto_geriatrico": (["Absorvente Geriátrico Bigfral"], ["Absorvente Sym Sem Abas"]),
        }
        for nome_filtro, (excluidos, mantidos) in casos.items():
            df = pd.DataFrame({
                "EAN": [str(i) for i in range(len(excluidos) + len(mantidos))],
                "PRODUCT_NAME": excluidos + mantidos,
            })
            out = apply_universe_exclusions(df, [nome_filtro])
            self.assertEqual(
                out["PRODUCT_NAME"].tolist(), mantidos,
                f"filtro {nome_filtro}: sobrou {out['PRODUCT_NAME'].tolist()}",
            )


if __name__ == "__main__":
    unittest.main()


class TestExclusionsW3(unittest.TestCase):
    """Só os 2 filtros W3 validados por spot-check (0 falsos+ na baseline)."""

    def test_nao_cereal_pega_geleia_mocoto_preserva_barra(self):
        from parts.universe_filters import apply_universe_exclusions
        df = pd.DataFrame({
            "EAN": ["1", "2", "3", "4"],
            "PRODUCT_NAME": [
                "Geléia de Mocotó Neropolis Puro 400g",       # sai
                "Geléia de Morango São Lourenço Diet 200g",    # sai
                "Barra de Cereal Goiabada Candy Katy 20g",     # FICA (sabor doce)
                "Aveia em Flocos Quaker 200g",                 # fica
            ],
        })
        out = apply_universe_exclusions(df, ["nao_cereal"])
        self.assertEqual(out["EAN"].tolist(), ["3", "4"])

    def test_agua_de_coco_intruso(self):
        from parts.universe_filters import apply_universe_exclusions
        df = pd.DataFrame({
            "EAN": ["1", "2", "3"],
            "PRODUCT_NAME": [
                "Água de Coco Cocobom 1l",           # sai
                "Água Mineral Crystal 1,5l",         # fica
                "Água Tônica Antarctica 350ml",      # fica
            ],
        })
        out = apply_universe_exclusions(df, ["agua_de_coco"])
        self.assertEqual(out["EAN"].tolist(), ["2", "3"])

    def test_defaults_de_slug_ligados(self):
        from parts.config_loader import _DEFAULT_UNIVERSE_EXCLUSIONS
        self.assertEqual(
            _DEFAULT_UNIVERSE_EXCLUSIONS["aveias_e_cereais__mercado"], ("nao_cereal",)
        )
        self.assertEqual(
            _DEFAULT_UNIVERSE_EXCLUSIONS["agua__bebidas"], ("agua_de_coco",)
        )
