# -*- coding: utf-8 -*-
"""Torna a raiz do similis importável nos testes (substitui os sys.path.insert
que cada arquivo de teste duplicava)."""
import os
import sys

_SIMILIS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _SIMILIS_ROOT not in sys.path:
    sys.path.insert(0, _SIMILIS_ROOT)
