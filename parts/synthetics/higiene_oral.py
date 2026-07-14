# -*- coding: utf-8 -*-
"""Sintéticos de higiene oral: ``fluor``.

Motivação (judge sobre a baseline): 215× "sem flúor vs com flúor: restrição
pediátrica" em creme_e_gel_dental_infantil + 39× na versão adulta. Criança em
regime sem flúor (deglutição) não pode receber creme com flúor no lugar — e o
inverso perde a proteção. Eixo de SEGURANÇA → hard_filter.
"""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register

# Mesma convenção do `lactose`: só classifica como 'sem_fluor' quando o nome
# DECLARA a ausência (produto com flúor raramente rotula o óbvio). Default
# 'com_fluor' — conservador para o catálogo brasileiro, onde a regra é ter.
_SEM_FLUOR_PATTERN = re.compile(
    r"sem\s*fl[uú]or|zero\s*fl[uú]or|0%?\s*de?\s*fl[uú]or|"
    r"livre\s*de\s*fl[uú]or|fluoride[\s-]*free|fluor[\s-]*free|"
    r"n[ãa]o\s*cont[ée]m\s*fl[uú]or",
    re.IGNORECASE,
)


@register("fluor")
def compute_fluor(df: pd.DataFrame, config) -> pd.Series:
    """'sem_fluor' se declarado no nome, senão 'com_fluor'."""
    return df["PRODUCT_NAME"].map(
        lambda n: "sem_fluor" if _SEM_FLUOR_PATTERN.search(n or "") else "com_fluor"
    )
