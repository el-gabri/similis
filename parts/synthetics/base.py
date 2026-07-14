# -*- coding: utf-8 -*-
"""Infra do registro de atributos sintéticos.

Um atributo sintético é uma coluna derivada (em geral do ``PRODUCT_NAME`` e/ou
de keys do ``skus_metadata``) que não existe como key no metadata. Cada
extrator se registra com:

  - ``name``: nome da coluna produzida (é o nome usado no ``infos.yaml``);
  - ``compute``: função ``(df, config) -> pd.Series`` alinhada às linhas;
  - ``required_metadata_keys``: keys do ``skus_metadata`` que o ``data_loader``
    precisa pivotar para este sintético funcionar.

O registro é a ÚNICA fonte de verdade: ``data_loader`` deriva dele quais keys
auxiliares buscar e ``normalizer`` deriva dele o que computar — antes eram
dois conjuntos mantidos à mão que precisavam bater com as funções.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet

import pandas as pd


@dataclass(frozen=True)
class SyntheticSpec:
    name: str
    compute: Callable[[pd.DataFrame, object], pd.Series]
    required_metadata_keys: FrozenSet[str] = field(default_factory=frozenset)


REGISTRY: Dict[str, SyntheticSpec] = {}


def register(name: str, required_metadata_keys=()):
    """Decorator: registra ``fn(df, config) -> pd.Series`` como sintético."""

    def _wrap(fn):
        REGISTRY[name] = SyntheticSpec(
            name=name,
            compute=fn,
            required_metadata_keys=frozenset(required_metadata_keys),
        )
        return fn

    return _wrap


def resolve_column(df: pd.DataFrame, attr: str):
    """Coluna do df cujo nome bate case-insensitive com ``attr`` (ou None)."""
    lookup = {str(c).lower(): c for c in df.columns}
    return lookup.get(str(attr).lower())
