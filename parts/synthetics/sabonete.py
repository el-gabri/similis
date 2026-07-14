# -*- coding: utf-8 -*-
"""Sintéticos de sabonete: ``forma_sabonete`` e ``tipo_sabonete``."""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register

# forma_sabonete: barra vs líquido — eixo NÚMERO 1 (barra de 100g não substitui
# líquido de 1-2L). Como hard_filter também deixa a partição homogênea em
# unidade (barra=g, líquido=ml). Sinal 1: a PALAVRA (cobrindo erros de
# cadastro). Sinal 2 (mais confiável): a UNIDADE — volume em ml/L ⇒ líquido.
_SABONETE_LIQUIDO_PALAVRA = re.compile(
    r"l[íi]qu[íi]d|\bl[íi]q\b|\bliq\.", re.IGNORECASE
)
_SABONETE_VOLUME = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:ml|mls|l|lt|lts|litros?)\b", re.IGNORECASE
)


@register("forma_sabonete")
def compute_forma_sabonete(df: pd.DataFrame, config) -> pd.Series:
    """'liquido' se palavra OU unidade de volume no nome; senão 'barra'."""

    def _one(name):
        n = name or ""
        if _SABONETE_LIQUIDO_PALAVRA.search(n) or _SABONETE_VOLUME.search(n):
            return "liquido"
        return "barra"

    return df["PRODUCT_NAME"].map(_one)


# tipo_sabonete: função/uso, soft_boost. Ordem da mais específica/crítica para
# a genérica ('antiacne' antes de 'facial': um facial-antiacne cai no funcional).
_TIPO_SABONETE_PATTERNS = [
    ("antisseptico", re.compile(
        r"antiss[ée]ptico|anti[\s-]*s[ée]ptico|antibacteriano|antimicrobiano|"
        r"antif[úu]ngico|germicida|\bmicosan\b|enxofre",
        re.IGNORECASE)),
    ("infantil", re.compile(
        r"\bbaby\b|beb[êe]\b|infantil|\bkids\b|tra\s*la\s*la",
        re.IGNORECASE)),
    ("intimo", re.compile(
        r"[íi]ntim[oa]|ginecol[óo]gic|higiene\s*[íi]ntima",
        re.IGNORECASE)),
    ("antiacne", re.compile(
        r"\bacne\b|oleosidade|pele\s*oleosa|limpeza\s*profunda|\bcravos?\b|"
        r"\boily\b|seborr",
        re.IGNORECASE)),
    ("facial", re.compile(
        r"facial|\brosto\b|\bface\b|demaquilante|pós[\s-]*maquiagem|"
        r"p[óo]s[\s-]*maquiagem",
        re.IGNORECASE)),
]


@register("tipo_sabonete")
def compute_tipo_sabonete(df: pd.DataFrame, config) -> pd.Series:
    """'antisseptico'|'infantil'|'intimo'|'antiacne'|'facial'|'comum' (default)."""

    def _one(name):
        n = name or ""
        for label, pat in _TIPO_SABONETE_PATTERNS:
            if pat.search(n):
                return label
        return "comum"

    return df["PRODUCT_NAME"].map(_one)
