# -*- coding: utf-8 -*-
"""Sintéticos de bebidas/alimentos: ``forma_bebida``.

Motivação (judge sobre a baseline): 940× "achocolatado em pó sugerido para
bebida pronta RTD" em achocolatado_pronto (76.7% grave — a pior taxa da
rodada); 52× "whey em pó no lugar de barra proteica"; 21× "cápsula suplemento
no lugar de chá". Pó/cápsula não substitui produto pronto para consumo.
"""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register

# Conservador: detecta APENAS as formas "não prontas" declaradas no nome
# (pó, solúvel, cápsula). O resto cai em '' (pronto/indefinido) e particiona
# junto — não tenta adivinhar RTD, que raramente é declarado no nome.
# Ordem: cápsula antes de pó ("cápsulas de café em pó" é cápsula).
_FORMA_BEBIDA_PATTERNS = [
    ("capsula", re.compile(r"c[áa]psulas?\b|\bcaps\b|comprimidos?\b", re.IGNORECASE)),
    ("po", re.compile(
        r"\bem\s*p[óo]\b|sol[úu]vel|\bp[óo]\s*para\s*preparo|mistura\s*para\s*preparo",
        re.IGNORECASE)),
]


@register("forma_bebida")
def compute_forma_bebida(df: pd.DataFrame, config) -> pd.Series:
    """'po' | 'capsula' | '' (pronto/não declarado)."""

    def _one(name):
        n = name or ""
        for label, pat in _FORMA_BEBIDA_PATTERNS:
            if pat.search(n):
                return label
        return ""

    return df["PRODUCT_NAME"].map(_one)
