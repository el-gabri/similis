# -*- coding: utf-8 -*-
"""Sintéticos de leite em pó: ``tipo_leite``, ``base_leite`` e ``lactose``."""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register

# Ordem importa: "semidesnatado" antes de "desnatado" e "integral" para não
# classificar errado por substring.
_TIPO_LEITE_PATTERNS = [
    ("semidesnatado", re.compile(r"semi[\s-]*desnatado|semidesnatado|semi[\s-]*desn", re.IGNORECASE)),
    ("desnatado",     re.compile(r"desnatado|desnat\b|\bdesn\b|\blight\b|zero\s*gordura|skim", re.IGNORECASE)),
    ("integral",      re.compile(r"integral|\bwhole\b", re.IGNORECASE)),
]


@register("tipo_leite")
def compute_tipo_leite(df: pd.DataFrame, config) -> pd.Series:
    """Teor de gordura: 'integral' | 'desnatado' | 'semidesnatado' | ''.

    '' quando o nome não declara — conservador: não inventa teor. Como
    hard_filter, os "sem tipo declarado" particionam juntos.
    """

    def _one(name):
        n = name or ""
        for label, pat in _TIPO_LEITE_PATTERNS:
            if pat.search(n):
                return label
        return ""

    return df["PRODUCT_NAME"].map(_one)


# Base do produto: leite de vaca (default) vs. composto lácteo, bebida vegetal,
# leite de cabra, pó para preparo. Vegetais primeiro (alguns trazem "leite" no nome).
_BASE_LEITE_PATTERNS = [
    ("soja",     re.compile(r"\bsoja\b|extrato de soja|\bsoy\b|supra\s*soy|lev\s*soy|soymilk", re.IGNORECASE)),
    ("arroz",    re.compile(r"\barroz\b", re.IGNORECASE)),
    ("amendoa",  re.compile(r"am[êe]ndoa", re.IGNORECASE)),
    ("aveia",    re.compile(r"\baveia\b", re.IGNORECASE)),
    ("coco",     re.compile(r"\bcoco\b", re.IGNORECASE)),
    ("cabra",    re.compile(r"\bcabra\b", re.IGNORECASE)),
    ("composto", re.compile(r"composto\s*l[áa]cteo|\bcomposto\b|p[óo]\s*para\s*preparo|sabor\s*leite|modificado|adoçado|\ball\s*lac\b", re.IGNORECASE)),
]


@register("base_leite")
def compute_base_leite(df: pd.DataFrame, config) -> pd.Series:
    """Base: 'soja'|'arroz'|'amendoa'|'aveia'|'coco'|'cabra'|'composto'|'vaca' (default)."""

    def _one(name):
        n = name or ""
        for label, pat in _BASE_LEITE_PATTERNS:
            if pat.search(n):
                return label
        return "vaca"

    return df["PRODUCT_NAME"].map(_one)


# Lactose: binário. 'sem_lactose' só quando declarado explicitamente.
_SEM_LACTOSE_PATTERN = re.compile(
    r"sem\s*lactose|zero\s*lactose|0%?\s*lactose|deslactosad|s/\s*lactose|"
    r"lactofree|lacto\s*free|lac\s*free|lacfree|low\s*lactose|delactos",
    re.IGNORECASE,
)


@register("lactose")
def compute_lactose(df: pd.DataFrame, config) -> pd.Series:
    """'sem_lactose' se declarado no nome, senão 'com_lactose'."""
    return df["PRODUCT_NAME"].map(
        lambda n: "sem_lactose" if _SEM_LACTOSE_PATTERN.search(n or "") else "com_lactose"
    )
