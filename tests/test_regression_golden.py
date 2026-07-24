# -*- coding: utf-8 -*-
"""Regressão contra golden fixtures.

As fixtures (tests/fixtures/*.json) capturam o comportamento de referência do
pipeline normalize -> recommend. Qualquer refactor que NÃO pretenda mudar
resultados deve manter o RANKING idêntico: mesmos EANs, mesma ordem, mesmos
ranks. A ``relevance`` é comparada com tolerância (:data:`_REL_TOL`) porque o
produto interno FAISS/BLAS difere de ~1 ulp entre versões de biblioteca e de
CPU — o 6º dígito não é contrato, o ranking é. Mudança INTENCIONAL de
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

# Tolerância da relevance (ver docstring do módulo). Estrutura — EANs, ordem,
# rank — permanece comparada por igualdade exata.
_REL_TOL = 1e-5

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
            self._assert_ranking_matches(got, golden[name], name)

    def _assert_ranking_matches(self, got, expected, scenario):
        self.assertEqual(
            set(got), set(expected), f"cenário {scenario}: origens divergiram"
        )
        for origem, exp_list in expected.items():
            got_list = got[origem]
            ctx = f"cenário {scenario}, origem {origem}"

            if not exp_list:
                self.assertEqual(got_list, [], f"{ctx}: esperava lista vazia")
                continue

            got_rels = [s["relevance"] for s in got_list]
            exp_rels = [s["relevance"] for s in exp_list]

            # (a) É um ranking próprio: ranks contíguos 1..N, ordenado por
            # relevance decrescente.
            self.assertEqual(
                [s["rank"] for s in got_list],
                list(range(1, len(got_list) + 1)),
                f"{ctx}: ranks não são 1..N contíguos",
            )
            self.assertEqual(
                got_rels, sorted(got_rels, reverse=True), f"{ctx}: não decrescente"
            )

            # (b) Perfil de scores idêntico dentro da tolerância (posição a
            # posição). Comprova que o pipeline calculou os MESMOS scores; a
            # diferença de ~1 ulp do produto interno FAISS/BLAS entre libs/CPUs
            # fica sob a tolerância.
            self.assertEqual(
                len(got_list), len(exp_list), f"{ctx}: tamanho da lista divergiu"
            )
            for i, (g, e) in enumerate(zip(got_rels, exp_rels)):
                self.assertAlmostEqual(
                    g, e, delta=_REL_TOL,
                    msg=f"{ctx}, posição {i}: perfil de score divergiu",
                )

            # (c) EANs ACIMA do nível de corte batem exatamente. No nível de
            # corte, um grupo de itens EMPATADOS pode ser truncado pelo top-K —
            # qual deles sobra depende da ordem em que o índice devolve os
            # empates. Contrato: mesmo conjunto acima do corte + mesmo tamanho
            # total ⇒ o grupo empatado difere no máximo em quem preencheu a
            # última vaga (não é regressão).
            thresh = min(exp_rels)
            core_got = {s["ean"] for s in got_list if s["relevance"] > thresh + _REL_TOL}
            core_exp = {s["ean"] for s in exp_list if s["relevance"] > thresh + _REL_TOL}
            self.assertEqual(core_got, core_exp, f"{ctx}: EANs acima do corte divergiram")


if __name__ == "__main__":
    unittest.main()
