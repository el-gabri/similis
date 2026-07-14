# -*- coding: utf-8 -*-
"""Sintéticos de puericultura: ``faixa_etaria_bebe``.

Motivação (judge): 28× "faixa etária chupeta incompatível (0-6m vs 6+m)" em
chupetas. Bico/fluxo/tamanho errado para a idade é eixo de segurança — vale
também para mamadeiras e bicos (mesma convenção de sizing por fase).
"""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register

# '' quando o nome não declara (particiona junto, sem inventar idade).
# Ordem: fase 2 antes de fase 1 — "6-18m" contém "6" mas não é 0-6.
_FAIXA_PATTERNS = [
    ("fase2", re.compile(
        r"6\s*(?:a|-|–)\s*18\s*m|\+\s*6\s*m|6\s*m\s*\+|acima\s*de\s*6\s*m|"
        r"a\s*partir\s*de\s*6\s*m|fase\s*2\b|tam(?:anho)?\s*2\b",
        re.IGNORECASE)),
    ("fase1", re.compile(
        r"0\s*(?:a|-|–)\s*6\s*m|at[ée]\s*6\s*m|rec[ée]m[\s-]*nascid|newborn|"
        r"\brn\b|fase\s*1\b|tam(?:anho)?\s*1\b",
        re.IGNORECASE)),
]


@register("faixa_etaria_bebe")
def compute_faixa_etaria_bebe(df: pd.DataFrame, config) -> pd.Series:
    """'fase1' (0-6m) | 'fase2' (6m+) | '' (não declarada)."""

    def _one(name):
        n = name or ""
        for label, pat in _FAIXA_PATTERNS:
            if pat.search(n):
                return label
        return ""

    return df["PRODUCT_NAME"].map(_one)
