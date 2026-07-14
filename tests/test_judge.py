import unittest

import pandas as pd

from parts import judge


class TestJudgeReshape(unittest.TestCase):
    def test_reshape_recommendations_flat_schema(self):
        pdf = pd.DataFrame(
            {
                "subcategoria": ["fraldas", "fraldas"],
                "ean_origem": ["1", "1"],
                "product_name_origem": ["Fralda G 30un", "Fralda G 30un"],
                "ean_sugestao": ["2", "3"],
                "product_name_sugestao": ["Fralda G 28un", "Fralda G 32un"],
                "rank": [2, 1],
                "relevance": [0.8, 0.9],
            }
        )

        registros = judge.reshape_to_origins(pdf, top_k=25)

        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["subcategoria"], "fraldas")
        self.assertEqual(registros[0]["origem_ean"], "1")
        self.assertEqual(registros[0]["sug_eans"], ["3", "2"])
        self.assertEqual(registros[0]["sug_nomes"], ["Fralda G 32un", "Fralda G 28un"])


if __name__ == "__main__":
    unittest.main()
