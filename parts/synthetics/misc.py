# -*- coding: utf-8 -*-
"""Sintéticos diversos: ``tipo_papinha`` e ``tipo_kit``."""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register

# Papinha: refeição (salgada) vs. sobremesa/lanche (doce). Prioridade SALGADA:
# quando há proteína/legume/sopa, classifica salgada (mesmo citando fruta).
# NÃO inclui 'batata'/'arroz' isolados (ambíguos: "batata doce", "mingau de arroz").
_PAPINHA_SALGADA_PATTERN = re.compile(
    r"carne|frango|peru|peito|galinha|\bovo\b|gema|feij[ãa]o|legume|hortali[çc]a|"
    r"sopa|sopinha|risot|strogonof|macarr[ãa]o|espaguet|lentilha|gr[ãa]o|"
    r"mandioqui|mandioca|abóbora|abobora|moranga|beterraba|"
    r"baroa|salgad|picadinho|caldo|bolonhesa|vegetai?s?|vegana?|"
    r"espinafre|abobrinha|brócolis|brocolis|ervilha|chuchu|inhame",
    re.IGNORECASE,
)
_PAPINHA_DOCE_PATTERN = re.compile(
    r"ma[çc][ãa]|banana|pera|pêra|ameixa|manga|mam[ãa]o|morango|fruta|frutas|"
    r"iogurte|yogo|uva|goiaba|laranja|p[êe]ssego|abacaxi|mirtilo|framboesa|"
    r"pitaya|maracuj[áa]|sobremesa|\bdoce\b|mel\b|batata[\s-]*doce|mingau|aveia|açaí|acai",
    re.IGNORECASE,
)


@register("tipo_papinha")
def compute_tipo_papinha(df: pd.DataFrame, config) -> pd.Series:
    """'salgada' | 'doce' | '' (indeterminado — particiona junto, sem inventar)."""

    def _one(name):
        n = name or ""
        if _PAPINHA_SALGADA_PATTERN.search(n):
            return "salgada"
        if _PAPINHA_DOCE_PATTERN.search(n):
            return "doce"
        return ""

    return df["PRODUCT_NAME"].map(_one)


# Kit de viagem: recipiente (frascos) vs continente (necessaire). Universo
# pequeno (~26 EANs) — soft_boost para não orfanar. 'frascos' tem prioridade.
_TIPO_KIT_PATTERNS = [
    ("frascos", re.compile(
        r"\bfrascos?\b|bisnagas?|\bpotes?\b|\bfunil\b|\bdobr[áa]ve", re.IGNORECASE)),
    ("necessaire", re.compile(
        r"necess[áa]ire|\bestojo\b|\bbolsa\b", re.IGNORECASE)),
]


@register("tipo_kit")
def compute_tipo_kit(df: pd.DataFrame, config) -> pd.Series:
    """'frascos' | 'necessaire' | 'outro' (default)."""

    def _one(name):
        n = name or ""
        for label, pat in _TIPO_KIT_PATTERNS:
            if pat.search(n):
                return label
        return "outro"

    return df["PRODUCT_NAME"].map(_one)


# --- Baterias: tipo/formato (judge: 250× "tipo de bateria incompatível:
# AAA vs AA" em baterias_para_monitores — AA não substitui AAA, ponto). -----
# Ordem: 'aaa' ANTES de 'aa' (substring). 'botao' cobre células de relógio/
# monitor (CR2032, LR44...). '' quando o nome não declara.
_TIPO_BATERIA_PATTERNS = [
    ("aaa", re.compile(r"\baaa\b|\bpalito\b", re.IGNORECASE)),
    ("aa", re.compile(r"\baa\b|\bpequena\b", re.IGNORECASE)),
    ("9v", re.compile(r"\b9\s*v(?:olts?)?\b", re.IGNORECASE)),
    ("botao", re.compile(r"\bcr\s*\d{3,4}\b|\blr\s*\d{2,4}\b|\bbot[ãa]o\b|\bmoeda\b", re.IGNORECASE)),
]


@register("tipo_bateria")
def compute_tipo_bateria(df: pd.DataFrame, config) -> pd.Series:
    """'aa' | 'aaa' | '9v' | 'botao' | '' (não declarado)."""

    def _one(name):
        n = name or ""
        for label, pat in _TIPO_BATERIA_PATTERNS:
            if pat.search(n):
                return label
        return ""

    return df["PRODUCT_NAME"].map(_one)


# --- Água terapêutica: boricada vs oxigenada (judge: 216× "água boricada vs
# oxigenada: uso terapêutico distinto"). Oxigenada ainda tem volumagem (10/20/
# 30/40 vol), mas o eixo crítico é o tipo. '' para o que não declara. --------
_TIPO_AGUA_PATTERNS = [
    ("boricada", re.compile(r"boricad|[áa]cido\s*b[óo]rico", re.IGNORECASE)),
    ("oxigenada", re.compile(r"oxigenad|per[óo]xido", re.IGNORECASE)),
]


@register("tipo_agua_terapeutica")
def compute_tipo_agua_terapeutica(df: pd.DataFrame, config) -> pd.Series:
    """'boricada' | 'oxigenada' | '' (não declarado)."""

    def _one(name):
        n = name or ""
        for label, pat in _TIPO_AGUA_PATTERNS:
            if pat.search(n):
                return label
        return ""

    return df["PRODUCT_NAME"].map(_one)
