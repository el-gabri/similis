# -*- coding: utf-8 -*-
"""Sintéticos de papel/lenço: ``tipo_lenco`` e ``tipo_folha``."""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register

# Eixo de uso (assoar/limpeza seca vs. úmida). Universo pequeno: soft_boost.
_LENCO_UMEDECIDO_PATTERN = re.compile(
    r"umedecid|umidecid|wipes|toalha|cleansing|refreshing|"
    r"demaquil|micelar|\bumido\b|umida",
    re.IGNORECASE,
)


@register("tipo_lenco")
def compute_tipo_lenco(df: pd.DataFrame, config) -> pd.Series:
    """'umedecido' se o nome declara úmido/wipes/limpeza, senão 'seco'."""
    return df["PRODUCT_NAME"].map(
        lambda n: "umedecido" if _LENCO_UMEDECIDO_PATTERN.search(n or "") else "seco"
    )


# tipo_folha é o eixo discriminante principal do papel higiênico (folha tripla
# não substitui simples). Ordem importa: quádrupla > tripla > dupla > simples.
_TIPO_FOLHA_PATTERNS = [
    ("quadrupla", re.compile(r"folha?s?\s*qu[áa]drupla?s?|qu[áa]drupla?s?\b|qu[áa]druple", re.IGNORECASE)),
    ("tripla",  re.compile(r"folha?s?\s*tripla?s?|tripla?s?\b|\bvip\s*3\b|\bvip3\b|tr[ií]plice", re.IGNORECASE)),
    ("dupla",   re.compile(r"folha?s?\s*dupla?s?|dupla?s?\b|duetto|double", re.IGNORECASE)),
    ("simples", re.compile(r"folha?s?\s*simples|simples\b|folha\s*[úu]nica|single", re.IGNORECASE)),
]


@register("tipo_folha")
def compute_tipo_folha(df: pd.DataFrame, config) -> pd.Series:
    """'quadrupla' | 'tripla' | 'dupla' | 'simples' | '' (não declarado)."""

    def _one(name):
        n = name or ""
        for label, pat in _TIPO_FOLHA_PATTERNS:
            if pat.search(n):
                return label
        return ""

    return df["PRODUCT_NAME"].map(_one)
