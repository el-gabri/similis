# -*- coding: utf-8 -*-
"""Normalização: sintéticos configurados, limpeza e texto canônico.

Os extratores de atributos sintéticos vivem em ``parts/synthetics/`` (um
módulo por domínio, registrados em ``REGISTRY``); parsing de unidades em
``parts/units.py``; filtros de universo em ``parts/universe_filters.py``.
Este módulo só orquestra: computa os sintéticos que a config pede, aplica
``universe_exclusions``, limpa colunas e monta o ``text_canon``.
"""
from __future__ import annotations

from typing import List

import pandas as pd

from parts.config_loader import SubcategoryConfig
from parts.synthetics import REGISTRY
from parts.synthetics.base import resolve_column as _resolve_column
from parts.synthetics.fraldas import normalize_diaper_size as _normalize_diaper_size  # noqa: F401 (compat)
from parts.text import clean_text, tokenize_for_removal as _tokenize_for_removal
from parts.units import (  # noqa: F401 (re-export de compatibilidade p/ notebooks)
    convert_unit,
    parse_mass_volume,
    parse_metragem,
    parse_pack_size,
)
from parts.universe_filters import apply_universe_exclusions


def _required_synthetics(df: pd.DataFrame, config: SubcategoryConfig) -> List[str]:
    """Sintéticos a computar: os configurados + ``quantity_norm`` quando o
    filtro de quantidade está ativo (o ranker lê a coluna mesmo sem regra).

    Só computa o que a config usa — o normalizer antigo computava TODOS os
    extratores para TODA subcategoria (15 ``df.apply`` num universo de
    shampoo que só usa ``quantity_norm``).
    """
    wanted = [a for a in config.all_attributes if a in REGISTRY]
    if config.quantity_ratio_bounds is not None and "quantity_norm" not in wanted:
        wanted.append("quantity_norm")
    # Ordem estável: a ordem de registro (histórica), não a da config.
    order = {name: i for i, name in enumerate(REGISTRY)}
    return sorted(set(wanted), key=lambda a: order[a])


def _compute_synthetic_columns(df: pd.DataFrame, config: SubcategoryConfig) -> pd.DataFrame:
    """Cria as colunas sintéticas exigidas pela config (idempotente:
    coluna já presente no df não é recalculada)."""
    df = df.copy()
    for name in _required_synthetics(df, config):
        if name not in df.columns:
            df[name] = REGISTRY[name].compute(df, config)
    return df


def normalize_dataframe(df: pd.DataFrame, config: SubcategoryConfig) -> pd.DataFrame:
    """Normaliza colunas de atributos e adiciona ``text_canon``."""
    dup = df.columns[df.columns.duplicated()].tolist()
    if dup:
        raise ValueError(
            f"DataFrame com colunas duplicadas: {sorted(set(dup))} — "
            "verifique o pivot do data_loader (uma key do skus_metadata "
            "colidindo com coluna do datasheet base?)."
        )
    out = df.copy()
    if "EAN" not in out.columns and "ean" in out.columns:
        out["EAN"] = out["ean"].astype(str)
    if "PRODUCT_NAME" not in out.columns:
        for cand in ("product_name", "PRODUCT_NAME_FINAL"):
            col = _resolve_column(out, cand)
            if col:
                out["PRODUCT_NAME"] = out[col]
                break
        if "PRODUCT_NAME" not in out.columns:
            out["PRODUCT_NAME"] = ""

    out = _compute_synthetic_columns(out, config)

    # Filtros de universo declarados na config (remove ORIGEM e CANDIDATO).
    out = apply_universe_exclusions(
        out, getattr(config, "universe_exclusions", ()) or ()
    )

    out["PRODUCT_NAME_CLEAN"] = out["PRODUCT_NAME"].map(clean_text)
    desc_col = _resolve_column(out, "product_description")
    if desc_col is None:
        out["product_description"] = ""
        desc_col = "product_description"
    out["PRODUCT_DESCRIPTION_CLEAN"] = out[desc_col].map(clean_text)

    for rule in config.rules:
        col = _resolve_column(out, rule.attribute)
        if col is None:
            out[rule.attribute] = ""
            col = rule.attribute
        out[col] = out[col].map(clean_text)

    out["text_canon"] = _build_text_canon_series(out, config)
    return out


def _build_text_canon_series(df: pd.DataFrame, config: SubcategoryConfig) -> pd.Series:
    """``text_canon`` vetorizado por regra (não por linha×regra×coluna).

    Resolve o mapa regra→coluna UMA vez e concatena Series; a remoção de
    tokens de hard_filter continua por linha (depende dos valores da linha).
    Byte-idêntico ao ``build_canonical_text`` aplicado linha a linha.
    """
    n = len(df)
    if n == 0:
        return pd.Series([], dtype=str)

    name = df["PRODUCT_NAME_CLEAN"].fillna("").astype(str)
    desc = df["PRODUCT_DESCRIPTION_CLEAN"].fillna("").astype(str)

    # partes por linha: nome + descrição (se != nome), depois regras repetidas.
    parts = [[t] if t else [] for t in name]
    for i, (nm, ds) in enumerate(zip(name, desc)):
        if ds and ds != nm:
            parts[i].append(ds)

    col_lookup = {str(c).lower(): c for c in df.columns}
    for rule in config.soft_boost_rules + config.text_only_rules:
        col = col_lookup.get(str(rule.attribute).lower())
        if col is None:
            continue
        repeat = max(1, int(round(rule.weight * 3)))
        vals = df[col].map(clean_text)
        for i, val in enumerate(vals):
            if val:
                parts[i].extend([val] * repeat)

    hard_cols = [
        col_lookup.get(str(r.attribute).lower())
        for r in config.hard_filter_rules
    ]
    hard_cols = [c for c in hard_cols if c is not None]

    out_texts = []
    for i in range(n):
        text = clean_text(" ".join(parts[i]))
        if hard_cols:
            hard_tokens = set()
            for c in hard_cols:
                hard_tokens.update(_tokenize_for_removal(str(df.iloc[i][c])))
            if hard_tokens:
                text = " ".join(t for t in text.split() if t not in hard_tokens)
        out_texts.append(text.strip() or name.iloc[i])
    return pd.Series(out_texts, index=df.index)


# ---------------------------------------------------------------------------
# Compat: assinatura antiga (linha a linha), usada por testes/notebooks.
# ---------------------------------------------------------------------------
def _row_get(row, key: str, default: str = ""):
    if isinstance(row, pd.Series):
        return row.get(key, default) if key in row.index else default
    return row.get(key, default)


def _row_has(row, key: str) -> bool:
    if isinstance(row, pd.Series):
        return key in row.index
    return key in row


def build_canonical_text(row, config: SubcategoryConfig, columns) -> str:
    parts: List[str] = []
    name = _row_get(row, "PRODUCT_NAME_CLEAN") or clean_text(_row_get(row, "PRODUCT_NAME", ""))
    if name:
        parts.append(name)
    description = _row_get(row, "PRODUCT_DESCRIPTION_CLEAN") or clean_text(
        _row_get(row, "product_description", "")
    )
    if description and description != name:
        parts.append(description)

    hard_tokens = set()
    col_lookup = {str(c).lower(): c for c in columns}
    for rule in config.hard_filter_rules:
        col = col_lookup.get(str(rule.attribute).lower())
        if col and _row_has(row, col):
            hard_tokens.update(_tokenize_for_removal(str(_row_get(row, col))))

    for rule in config.soft_boost_rules + config.text_only_rules:
        col = col_lookup.get(str(rule.attribute).lower())
        if col is None or not _row_has(row, col):
            continue
        val = clean_text(_row_get(row, col))
        if not val:
            continue
        repeat = max(1, int(round(rule.weight * 3)))
        for _ in range(repeat):
            parts.append(val)

    text = " ".join(parts)
    text = clean_text(text)
    if hard_tokens:
        tokens = [t for t in text.split() if t not in hard_tokens]
        text = " ".join(tokens)
    return text.strip() or name
