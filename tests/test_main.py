import importlib.util
import os
import sys
import unittest

_SIMILIS_ROOT = os.path.join(os.path.dirname(__file__), "..")
_MAIN_PATH = os.path.join(_SIMILIS_ROOT, "main.py")


def _load_main_module():
    spec = importlib.util.spec_from_file_location("similis_main", _MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class TestMainArgs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _load_main_module()

    def test_parse_cli_args_single_subcategory(self):
        args = self.main.parse_cli_args(["main.py", "fraldas", "predict_staging", "20"])

        self.assertEqual(args.subcategories, ["fraldas"])
        self.assertEqual(args.mode, "predict_staging")
        self.assertEqual(args.top_k_default, 20)

    def test_parse_cli_args_list_subcategories(self):
        args = self.main.parse_cli_args(
            ["main.py", '["fraldas", "talco"]', "predict", "50"]
        )

        self.assertEqual(args.subcategories, ["fraldas", "talco"])
        self.assertEqual(args.mode, "predict")
        self.assertEqual(args.top_k_default, 50)

    def test_output_target_for_mode(self):
        self.assertEqual(self.main._output_target_for_mode("predict"), "prod")
        self.assertEqual(self.main._output_target_for_mode("predict_all"), "prod")
        self.assertEqual(self.main._output_target_for_mode("predict_staging"), "staging")
        self.assertEqual(self.main._output_target_for_mode("predict_all_staging"), "staging")

    def test_subcategories_for_predict_all_defaults_when_empty(self):
        subs = self.main._subcategories_for_mode("predict_all", [])

        self.assertEqual(subs, self.main.FARMA_SUBCATEGORIES_DEFAULT)

    def test_subcategories_for_predict_all_honors_explicit_list(self):
        subs = self.main._subcategories_for_mode("predict_all", ["fraldas"])

        self.assertEqual(subs, ["fraldas"])


if __name__ == "__main__":
    unittest.main()
