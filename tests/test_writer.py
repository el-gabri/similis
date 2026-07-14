import json
import unittest

import pandas as pd

from parts.writer import (
    FLAT_COLUMN_NAMES,
    RECOMMENDATIONS_COLUMN_NAMES,
    prepare_recommendations_output,
)


class TestWriterContract(unittest.TestCase):
    def test_prepare_recommendations_output_preserves_contract(self):
        recs = pd.DataFrame(
            {
                "ean_origem": ["1", "2"],
                "sugestoes": [
                    [{"ean": "3", "relevance": 0.9, "rank": 1}],
                    [],
                ],
            }
        )
        name_by_ean = {
            "1": "Produto Origem 1",
            "2": "Produto Origem 2",
            "3": "Produto Sugestao",
        }

        nested, flat, run_date = prepare_recommendations_output(
            recs,
            "fraldas",
            "abc123",
            model_version="test-model",
            run_date="2026-06-25",
            name_by_ean=name_by_ean,
        )

        self.assertEqual(run_date, "2026-06-25")
        self.assertEqual(nested.columns.tolist(), list(RECOMMENDATIONS_COLUMN_NAMES))
        self.assertEqual(flat.columns.tolist(), list(FLAT_COLUMN_NAMES))

        first = nested[nested["ean_origem"] == "1"].iloc[0]
        self.assertEqual(first["product_name_origem"], "Produto Origem 1")
        self.assertEqual(first["n_sugestoes"], 1)
        self.assertEqual(first["subcategoria"], "fraldas")
        self.assertEqual(first["model_version"], "test-model")
        self.assertEqual(first["config_hash"], "abc123")
        self.assertEqual(first["date"], "2026-06-25")

        sugestoes = json.loads(first["sugestoes"])
        self.assertEqual(
            sugestoes,
            [{"ean": "3", "relevance": 0.9, "rank": 1, "product_name": "Produto Sugestao"}],
        )

        self.assertEqual(len(flat), 1)
        flat_row = flat.iloc[0].to_dict()
        self.assertEqual(flat_row["ean_origem"], "1")
        self.assertEqual(flat_row["ean_sugestao"], "3")
        self.assertEqual(flat_row["product_name_sugestao"], "Produto Sugestao")
        self.assertEqual(flat_row["rank"], 1)

    def test_nested_uses_legacy_slug_and_flat_keeps_composite(self):
        recs = pd.DataFrame(
            {
                "ean_origem": ["1"],
                "sugestoes": [[{"ean": "2", "relevance": 0.9, "rank": 1}]],
            }
        )
        # Caso real de slug legado abreviado: composto = creme_para_assaduras__…,
        # mas a aninhada deve gravar "creme_assaduras" (contrato do downstream).
        nested, flat, _ = prepare_recommendations_output(
            recs,
            "creme_para_assaduras__troca_de_fralda",
            "hash",
            run_date="2026-06-25",
            name_by_ean={"1": "Origem", "2": "Sugestao"},
            category_name="Troca de Fralda",
            subcategoria_nested="creme_assaduras",
        )

        # Aninhada: slug legado, sem colunas de categoria.
        self.assertEqual(nested.iloc[0]["subcategoria"], "creme_assaduras")
        self.assertNotIn("categoria", nested.columns.tolist())
        self.assertNotIn("category_name", nested.columns.tolist())

        # Flat: subcategoria = slug legado; categoria = slug da categoria.
        self.assertEqual(flat.iloc[0]["subcategoria"], "creme_assaduras")
        self.assertEqual(flat.iloc[0]["categoria"], "troca_de_fralda")
        self.assertNotIn("category_name", flat.columns.tolist())


if __name__ == "__main__":
    unittest.main()
