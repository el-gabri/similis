# -*- coding: utf-8 -*-
"""Sintéticos do universo de fraldas: ``size_norm`` e ``audience``."""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register, resolve_column
from parts.text import clean_text

# Vocabulário canônico de tamanhos de fralda. Comparado APÓS clean_text.
_DIAPER_SIZE_ALIASES = {
    "RN": "RN",
    "RECEM NASCIDO": "RN",
    "P": "P",
    "PEQUENO": "P",
    "M": "M",
    "MEDIO": "M",
    "G": "G",
    "GRANDE": "G",
    "XG": "XG",
    "EG": "XG",
    "EXG": "XG",
    "EXTRA GRANDE": "XG",
    "XXG": "XXG",
    "XXXG": "XXXG",
    "GG": "XG",
    "SXG": "XG",
}

# Tokens "G" sozinhos aparecem em embalagens ("200G"). Exigimos palavra inteira
# e preferimos os tokens mais específicos primeiro (XXXG antes de XXG antes de XG).
_DIAPER_SIZE_NAME_PATTERN = re.compile(
    r"\b(XXXG|XXG|EXG|SXG|XG|EG|GG|RN|P|M|G)\b",
    re.IGNORECASE,
)


def normalize_diaper_size(value: str) -> str:
    """Valor bruto -> rótulo canônico de tamanho ('' quando não identificado).

    '' faz o EAN cair numa partição "sem tamanho" no hard_filter — compete só
    com outros sem tamanho identificado.
    """
    if not value:
        return ""
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    if cleaned in _DIAPER_SIZE_ALIASES:
        return _DIAPER_SIZE_ALIASES[cleaned]
    match = _DIAPER_SIZE_NAME_PATTERN.search(cleaned)
    if match:
        return _DIAPER_SIZE_ALIASES.get(match.group(1).upper(), "")
    return ""


# NOTA (comportamento herdado): required_metadata_keys NÃO inclui brandSize —
# o data_loader antigo também não pedia. _compute usa brandSize apenas quando a
# coluna já está no df por outro motivo. Incluir aqui mudaria a cobertura do
# size_norm (mais dados carregados) e, portanto, os resultados.
@register("size_norm", required_metadata_keys={"sizeClassification", "diaperSize"})
def compute_size_norm(df: pd.DataFrame, config) -> pd.Series:
    """Tamanho canônico de fralda: sizeClassification -> diaperSize ->
    brandSize -> regex no PRODUCT_NAME.

    Comportamento herdado do normalizer antigo: quando NENHUMA das colunas de
    metadata existe no df, a coluna sai vazia (sem fallback do nome).
    """
    scols = [
        resolve_column(df, "sizeClassification"),
        resolve_column(df, "diaperSize"),
        resolve_column(df, "brandSize"),
    ]
    if not any(c is not None for c in scols):
        return pd.Series([""] * len(df), index=df.index)

    def _one(row):
        for col in scols:
            if not col:
                continue
            raw = row.get(col, "")
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            size = normalize_diaper_size(str(raw))
            if size:
                return size
        return normalize_diaper_size(str(row.get("PRODUCT_NAME", "") or ""))

    return df.apply(_one, axis=1)


# Marcas/termos de produto adulto/geriátrico que contaminam universos infantis.
# Padrões deliberadamente parciais para cobrir variações de cadastro.
_ADULT_PRODUCT_PATTERN = re.compile(
    r"geri[aá]t|incontin|\badult|dermadult|derm\s*adult|adultfral|adultcare|"
    r"\btena\b|bigfral|plenitud|\bmaster\s*plus\b|maxi\s*confort|vida\s+senhor",
    re.IGNORECASE,
)


@register("audience")
def compute_audience(df: pd.DataFrame, config) -> pd.Series:
    """'adulto' se geriátrico/incontinência/linha adulta, senão 'bebe'."""
    return df["PRODUCT_NAME"].map(
        lambda n: "adulto" if _ADULT_PRODUCT_PATTERN.search(n or "") else "bebe"
    )
