# -*- coding: utf-8 -*-
"""Escolha automática de template por subcategoria."""
from __future__ import annotations

import re
from typing import Iterable, Tuple

from parts.config_templates import (
    AGUA_TERAPEUTICA_TEMPLATE,
    ALIMENTOS_BEBIDAS_TEMPLATE,
    BATERIAS_TEMPLATE,
    BEBE_CUIDADOS_TEMPLATE,
    DEFAULT_TEMPLATE,
    DESODORANTE_TEMPLATE,
    FRALDAS_TEMPLATE,
    HIGIENE_ORAL_TEMPLATE,
    LATICINIOS_TEMPLATE,
    FORMULA_INFANTIL_TEMPLATE,
    HIGIENE_TEMPLATE,
    LEITE_EM_PO_TEMPLATE,
    PAPEL_LENCO_TEMPLATE,
    PAPINHA_TEMPLATE,
    SABONETE_TEMPLATE,
    ConfigTemplate,
)


PolicyRule = Tuple[re.Pattern, ConfigTemplate]


_POLICY_RULES: Iterable[PolicyRule] = [
    (re.compile(r"\bformula_infantil\b|f[óo]rmula", re.IGNORECASE), FORMULA_INFANTIL_TEMPLATE),
    (re.compile(r"\bleite_em_po\b|leite\s+em\s+p[oó]", re.IGNORECASE), LEITE_EM_PO_TEMPLATE),
    # Laticínios líquidos/frescos: DEPOIS do leite em pó (que tem template
    # próprio com base_leite/tipo_leite), ANTES do genérico alimentos_bebidas.
    (re.compile(r"leites__bebidas|leite_fermentado|iogurte", re.IGNORECASE), LATICINIOS_TEMPLATE),
    # Cremes/géis dentais (adulto + infantil): ANTES do higiene genérico, que
    # capturaria por "dental". Escova/fio dental seguem no higiene (flúor não
    # se aplica) — por isso o match é pelo prefixo creme_e_gel_dental.
    (re.compile(r"creme_e_gel_dental", re.IGNORECASE), HIGIENE_ORAL_TEMPLATE),
    # sem \b junto de "_" (underscore é word char e mata a fronteira)
    (re.compile(r"bateria|pilha", re.IGNORECASE), BATERIAS_TEMPLATE),
    (re.compile(r"agua_oxigenada", re.IGNORECASE), AGUA_TERAPEUTICA_TEMPLATE),
    (re.compile(r"\bfraldas?\b|fralda_geriatrica", re.IGNORECASE), FRALDAS_TEMPLATE),
    (re.compile(r"\bpapinha\b", re.IGNORECASE), PAPINHA_TEMPLATE),
    (re.compile(r"\bsabonete|sabonetes?\b", re.IGNORECASE), SABONETE_TEMPLATE),
    # Família Desodorante: casa pelo sufixo de CATEGORIA do slug composto
    # ("__desodorante"), não pela palavra solta — assim "Desodorante Íntimo"
    # (categoria Cuidado Íntimo) NÃO cai aqui e segue no template de higiene.
    (re.compile(r"__desodorante\b", re.IGNORECASE), DESODORANTE_TEMPLATE),
    (re.compile(r"\blencos?\b|len[çc]os?|rolos?|papel", re.IGNORECASE), PAPEL_LENCO_TEMPLATE),
    (
        re.compile(
            r"creme|assadura|shampoo|condicionador|absorvente|higiene|dental|"
            r"desodorante|repelente|protetor|hidratante|dermocosm",
            re.IGNORECASE,
        ),
        HIGIENE_TEMPLATE,
    ),
    (
        re.compile(
            r"alimento|bebida|suco|refrigerante|ch[áa]|caf[eé]|iogurte|leite|"
            r"achocolat|snack|biscoito|bolacha|doce|chocolate|sorvete|papinha",
            re.IGNORECASE,
        ),
        ALIMENTOS_BEBIDAS_TEMPLATE,
    ),
    (
        re.compile(
            r"beb[eê]|infantil|mamadeira|chupeta|mordedor|banheira|babador",
            re.IGNORECASE,
        ),
        BEBE_CUIDADOS_TEMPLATE,
    ),
]


def choose_template(slug: str, subcategory_name: str = "") -> ConfigTemplate:
    """Escolhe o primeiro template aplicável ao slug/nome literal.

    A regra é deliberadamente simples e auditável. O judge/monitoramento deve
    apontar quais subcategorias precisam sair do template genérico.
    """
    text = f"{slug or ''} {subcategory_name or ''}"
    for pattern, template in _POLICY_RULES:
        if pattern.search(text):
            return template
    return DEFAULT_TEMPLATE
