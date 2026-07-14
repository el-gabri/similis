import math
import unittest

from parts.units import (
    UNITS,
    convert_unit,
    parse_mass_volume,
    parse_metragem,
    parse_pack_size,
    parse_quantity,
)


class TestUnits(unittest.TestCase):
    def test_convert_unit_canonical(self):
        self.assertEqual(convert_unit("1,5 KG"), "1500 g")
        self.assertEqual(convert_unit("1 l"), "1000 ml")
        self.assertEqual(convert_unit("96 unidades"), "96 un")
        self.assertEqual(convert_unit(""), "not available")
        self.assertEqual(convert_unit("abc"), "not available")

    def test_parse_quantity_roundtrip_with_convert_unit(self):
        # Toda unidade da tabela deve parsear de volta para a mesma canônica.
        for unit, (canon, factor) in UNITS.items():
            parsed = parse_quantity(f"2 {unit}")
            self.assertIsNotNone(parsed, f"parse falhou para {unit!r}")
            value, got_canon = parsed
            self.assertEqual(got_canon, canon, f"canônica errada para {unit!r}")
            self.assertAlmostEqual(value, 2 * factor)

    def test_parse_quantity_equivalence(self):
        self.assertEqual(parse_quantity("1.5 kg"), parse_quantity("1500 g"))
        self.assertEqual(parse_quantity("1 l"), parse_quantity("1000 ml"))
        self.assertIsNone(parse_quantity("not available"))
        self.assertIsNone(parse_quantity(None))

    def test_parse_quantity_unknown_unit_passthrough(self):
        value, unit = parse_quantity("3 caixas")
        self.assertEqual((value, unit), (3.0, "caixas"))

    def test_parse_pack_size_multipack_before_simple(self):
        self.assertEqual(parse_pack_size("Fralda 6x22")["total"], 132)
        self.assertEqual(parse_pack_size("24 Pacotes Com 7un Cada")["total"], 168)
        self.assertEqual(parse_pack_size("Leve 12 Pague 11 Unidades")["total"], 12)
        self.assertEqual(parse_pack_size("Fralda G 58 Unidades")["total"], 58)

    def test_parse_mass_volume(self):
        self.assertEqual(parse_mass_volume("Leite Ninho 400g"), "400 g")
        self.assertEqual(parse_mass_volume("Creme 1,5l"), "1500 ml")
        self.assertEqual(parse_mass_volume("Nan Supreme 2"), "")

    def test_parse_metragem_word_boundary(self):
        # Regressão do bug da regex sombreada: com IGNORECASE, o lookahead
        # [A-Z] casava minúscula e "250ml" virava metragem "250".
        self.assertTrue(math.isnan(parse_metragem("Sabonete Liquido 250ml")))
        self.assertTrue(math.isnan(parse_metragem("Shampoo 200ml")))
        self.assertEqual(parse_metragem("Papel Higienico 30m"), 30.0)
        self.assertEqual(parse_metragem("Folha Dupla 12 Rolos 60 m"), 60.0)
        self.assertEqual(parse_metragem("Compacto 20m x 10cm"), 20.0)
        self.assertEqual(parse_metragem("Rolo 30 metros"), 30.0)

    def test_parse_metragem_plausibility_range(self):
        # fora de 5–600 m não é metragem de rolo
        self.assertTrue(math.isnan(parse_metragem("Fita 2m")))
        self.assertTrue(math.isnan(parse_metragem("Cabo 1000m")))
        self.assertEqual(parse_metragem("480m 30m x 10cm"), 480.0)


if __name__ == "__main__":
    unittest.main()
