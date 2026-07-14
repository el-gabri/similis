# -*- coding: utf-8 -*-
"""Sintéticos de desodorante: ``forma_desodorante`` e ``genero``.

Contexto: a categoria Desodorante já separa por forma na taxonomia (Aerosol,
Aerosol e Spray, Creme, Gel e Stick, Roll-on, Para os Pés) — cada subcategoria
DEVERIA ser homogênea em forma. Na prática, miscategorização upstream vaza
roll-on/loção/creme/pés para dentro de ``aerosol_e_spray`` (caso real: origem
"Loção ... Pump" com sugestões de aerossol; roll-on no rank 62; desodorante
para pés no rank 64). Como hard_filter, ``forma_desodorante`` particiona os
intrusos entre si (loção sugere loção) em vez de poluir — conservador e sem
descartar EANs.
"""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register

# Ordem importa (função antes de forma física):
#   1. 'pes' PRIMEIRO — desodorante para pés costuma também dizer "aerossol"
#      ("...Para Pés Controle De Odor Aerossol Jato Seco..."), e a função
#      (pés) importa mais que a forma para substituição.
#   2. 'colonia_splash' ANTES de 'aerosol' — "Desodorante Colônia Spray" é
#      perfumaria (função perfumar), não antitranspirante; caso real do
#      teste manual: colônias nos ranks 85-86 de origem antitranspirante.
#   3. 'rollon' e 'stick_gel' antes de 'aerosol' (formas específicas).
#   4. 'aerosol' antes de 'creme_locao' — "Deo Cream Aerossol" é uma LATA de
#      espuma cremosa: a forma física (aerossol) decide, não a textura.
#   5. '' quando o nome não declara — particiona os "sem forma" juntos,
#      sem inventar (mesma convenção do size_norm/tipo_leite).
_FORMA_PATTERNS = [
    ("pes", re.compile(
        r"para\s*(?:os\s*)?p[ée]s\b|\bp[ée]s\b", re.IGNORECASE)),
    ("colonia_splash", re.compile(
        r"col[ôo]nia|body\s*splash|\bsplash\b|deo\s*col[ôo]nia|eau\s*de",
        re.IGNORECASE)),
    ("rollon", re.compile(
        r"roll[\s._-]*on\b|\brolon\b", re.IGNORECASE)),
    ("stick_gel", re.compile(
        r"\bstick\b|\bgel\b", re.IGNORECASE)),
    ("aerosol", re.compile(
        r"aeross?ol|\bspray\b|\baero\b|body\s*spray|\bjato\s*seco\b",
        re.IGNORECASE)),
    ("creme_locao", re.compile(
        r"lo[çc][ãa]o|\bcreme\b|\bcream\b|\bpump\b|hidratante",
        re.IGNORECASE)),
]

# Fallback pelo packagingName do metadata quando o NOME não declara a forma —
# caso real: "Desodorante Tabu Baladeira 150ml" com packagingName=AEROSSOL
# caía em '' e aparecia para um body splash. Só formas INEQUÍVOCAS no
# packaging (aerossol/spray/roll-on/stick); FRASCO/LATA/EMBALAGEM são
# ambíguos e não inferem nada.
_FORMA_PACKAGING_PATTERNS = [
    ("rollon", re.compile(r"roll[\s._-]*on|rolon", re.IGNORECASE)),
    ("stick_gel", re.compile(r"\bstick\b", re.IGNORECASE)),
    ("aerosol", re.compile(r"aeross?ol|\bspray\b", re.IGNORECASE)),
]


@register("forma_desodorante", required_metadata_keys={"packagingName"})
def compute_forma_desodorante(df: pd.DataFrame, config) -> pd.Series:
    """Forma/função do desodorante: 'pes' | 'colonia_splash' | 'rollon' |
    'stick_gel' | 'aerosol' | 'creme_locao' | '' (não declarada).

    Fonte primária: PRODUCT_NAME; fallback: packagingName (só formas
    inequívocas)."""
    from parts.synthetics.base import resolve_column

    pcol = resolve_column(df, "packagingName")

    def _one(row):
        n = row.get("PRODUCT_NAME", "") or ""
        for label, pat in _FORMA_PATTERNS:
            if pat.search(n):
                return label
        if pcol is not None:
            p = row.get(pcol, "")
            if p is not None and not (isinstance(p, float) and pd.isna(p)):
                for label, pat in _FORMA_PACKAGING_PATTERNS:
                    if pat.search(str(p)):
                        return label
        return ""

    return df.apply(_one, axis=1)


# Gênero declarado no NOME (não inferir por marca): eixo de preferência, não
# de segurança — usado como soft_boost (favorece mesmo gênero no topo, sem
# esvaziar partição; masculino×feminino não é penalizado, só não é favorecido).
# '' (não declarado/unissex) nunca dá boost — strings vazias não batem.
_GENERO_PATTERNS = [
    ("masculino", re.compile(
        r"\bmen\b|\bfor\s*men\b|masculin|\bhomem\b|\bhomens\b|\bmasc\b|\bmale\b",
        re.IGNORECASE)),
    ("feminino", re.compile(
        r"feminin|\bwomen\b|\bwoman\b|mulher|\bfem\b|\bfemale\b",
        re.IGNORECASE)),
]


@register("genero")
def compute_genero(df: pd.DataFrame, config) -> pd.Series:
    """Gênero declarado: 'masculino' | 'feminino' | '' (não declarado)."""

    def _one(name):
        n = name or ""
        for label, pat in _GENERO_PATTERNS:
            if pat.search(n):
                return label
        return ""

    return df["PRODUCT_NAME"].map(_one)
