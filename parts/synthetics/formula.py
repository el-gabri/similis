# -*- coding: utf-8 -*-
"""Sintéticos de fórmula infantil: ``categoria_produto``, ``estagio``, ``tipo_formula``.

Eixos de SEGURANÇA — um substituto errado pode significar um bebê recebendo
produto impróprio; os três saem como hard_filter no infos.yaml. Derivados do
PRODUCT_NAME (o nome carrega rótulo regulatório e estágio de forma confiável;
o metadata é esparso/inflado neste universo).

ATENÇÃO: classificações clínicas (sobretudo tipo_formula) são um PRIMEIRO
CORTE e merecem revisão de nutrição/categoria antes de produção.
"""
from __future__ import annotations

import re

import pandas as pd

from parts.synthetics.base import register

_SUPLEMENTO_PATTERN = re.compile(
    r"suplemento|complemento\s*alimentar|\bfortini\b",
    re.IGNORECASE,
)
_COMPOSTO_LACTEO_PATTERN = re.compile(
    r"composto\s*l[áa]cteo|\benfagrow\b|\bneslac\b|\bnanlac\b|"
    r"ninho\s*fases|ninho\s*nutrigold|\bnutrigold\b",
    re.IGNORECASE,
)


@register("categoria_produto")
def compute_categoria_produto(df: pd.DataFrame, config) -> pd.Series:
    """'composto_lacteo' | 'suplemento' | 'formula_infantil' (default)."""

    def _one(name):
        n = name or ""
        if _COMPOSTO_LACTEO_PATTERN.search(n):
            return "composto_lacteo"
        if _SUPLEMENTO_PATTERN.search(n):
            return "suplemento"
        return "formula_infantil"

    return df["PRODUCT_NAME"].map(_one)


# 'pre' cobre prematuro/pré-termo (Pre Nan, Enfacare), NÃO 'pré-escolar'
# (que é 1+ ano e cai em estágio 3 via faixa).
_ESTAGIO_PRE_PATTERN = re.compile(
    r"prematur|enfacare|pr[eé][\s-]*termo|pr[eé][\s-]*nan|pre[\s-]*nan|"
    r"pr[eé][\s-]*transition|pre[\s-]*transition",
    re.IGNORECASE,
)
_ESTAGIO_FAIXA_PATTERNS = [
    ("3", re.compile(
        r"1\s*a\s*3\s*ano|9\s*mes\w*\s*a\s*2\s*ano|pr[eé][\s-]*escolar|"
        r"\b1\s*\+|a\s*partir\s*de\s*1\s*ano|ap[oó]s\s*1\s*ano|\b3\s*ano",
        re.IGNORECASE)),
    ("2", re.compile(
        r"6\s*a\s*12\s*mes|6\s*-\s*12\s*mes|\b612\s*mes|"
        r"a\s*partir\s*de\s*6\s*mes|\b6\s*12\s*mes",
        re.IGNORECASE)),
    ("1", re.compile(
        r"0\s*a\s*6\s*mes|0\s*-\s*6\s*mes|\b0\s*6\s*mes|\b06\s*mes|"
        r"at[ée]\s*6\s*mes|primeiro\s*semestre",
        re.IGNORECASE)),
]
# Número de estágio colado a linha conhecida (fallback), com GUARDA contra
# contagem de pacote ("2 Unidades", "800g").
_ESTAGIO_NUM_PATTERN = re.compile(
    r"(?:premium|pro|comfor|profutura|supreme|nestonutri|nestogeno|aptanutri|"
    r"aptamil|milupa|nanlac|neslac|nutrigold|fases|gold|advance|expert|sensitive|"
    r"optipro|\bnan\b|soja|soy|science|althera|pepti|nutri|infantil|f[óo]rmula)"
    r"\s*([1234])\b(?!\s*(?:un\b|unid|unidades?|g\b|kg|ml|mes|m[êe]s|ano))",
    re.IGNORECASE,
)


@register("estagio")
def compute_estagio(df: pd.DataFrame, config) -> pd.Series:
    """Estágio/faixa etária: '1' | '2' | '3' | 'pre' | '' (indeterminado).

    Prioridade: prematuro > faixa etária explícita > '1+' > número de estágio
    colado a linha conhecida. Estágio 4 (raro) agrupa com 3. '' quando nada
    casa. Eixo de MAIOR risco residual — conferir a fração de '' antes de
    promover a produção.
    """

    def _one(name):
        n = name or ""
        if _ESTAGIO_PRE_PATTERN.search(n):
            return "pre"
        for label, pat in _ESTAGIO_FAIXA_PATTERNS:
            if pat.search(n):
                return label
        m = _ESTAGIO_NUM_PATTERN.search(n)
        if m:
            num = m.group(1)
            return "3" if num == "4" else num
        return ""

    return df["PRODUCT_NAME"].map(_one)


# tipo_formula: classe terapêutica/especial. Ordem = da mais específica/crítica
# para a mais genérica. 'sem_lactose' NÃO entra aqui (eixo ortogonal `lactose`).
_TIPO_FORMULA_PATTERNS = [
    ("aminoacido", re.compile(
        r"neocate|alfamino|puramino|aminomed|anamix|amino\s*[áa]cido|"
        r"neo\s*advance|elemental",
        re.IGNORECASE)),
    ("ext_hidrolisada", re.compile(
        r"pregomin|pregestimil|alfar[ée]|althera|nutramigen|\bpepti\b|"
        r"extensamente\s*hidrolis|hidrolisad",
        re.IGNORECASE)),
    ("ha_parcial", re.compile(
        r"\bh\.?\s*a\.?\b|hipoalerg|hypoaller",
        re.IGNORECASE)),
    ("antirefluxo", re.compile(
        r"\ba\.?\s*r\.?\b|espessad|espessar|antirreflux|anti[\s-]?reflux|"
        r"regurgit|\brr\b",
        re.IGNORECASE)),
    ("soja", re.compile(r"\bsoja\b|\bsoy\b|nursoy", re.IGNORECASE)),
    ("conforto", re.compile(
        r"comfor|comfort|sensitive|gentlease|c[óo]lica|anti[\s-]?c[óo]lica",
        re.IGNORECASE)),
]


@register("tipo_formula")
def compute_tipo_formula(df: pd.DataFrame, config) -> pd.Series:
    """'aminoacido'|'ext_hidrolisada'|'ha_parcial'|'antirefluxo'|'soja'|'conforto'|'padrao'."""

    def _one(name):
        n = name or ""
        for label, pat in _TIPO_FORMULA_PATTERNS:
            if pat.search(n):
                return label
        return "padrao"

    return df["PRODUCT_NAME"].map(_one)
