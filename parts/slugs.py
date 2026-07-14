# -*- coding: utf-8 -*-
"""Lógica de slugs e identidade de subcategoria.

Identidade real do pipeline: o par ``(category_name, subcategory_name)``,
materializado no slug composto ``<subcategoria>__<categoria>`` (colapsa para
um termo quando os dois coincidem). O slug composto é chave de config, cache
de embeddings e argumento do job.

Slug LEGADO (coluna ``subcategoria`` das tabelas de saída): baseado só no
``subcategory_name``, com exceções históricas — ver ``nested_subcategoria``.
"""
from __future__ import annotations

import re
import unicodedata


def _slugify(text: str) -> str:
    """Slug ASCII estável: minúsculas, sem acento, não-alfanumérico -> ``_``."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "_", ascii_text)
    return ascii_text.strip("_")


def subcategory_slug(category_name: str, subcategory_name: str) -> str:
    """Slug composto ``<sub>__<cat>`` (ou só ``<sub>`` quando coincidem)."""
    sub_slug = _slugify(subcategory_name)
    cat_slug = _slugify(category_name)
    if not sub_slug:
        raise ValueError(f"subcategory_name vazio para categoria {category_name!r}")
    return sub_slug if sub_slug == cat_slug else f"{sub_slug}__{cat_slug}"


def simple_slug(subcategory_name: str) -> str:
    """Slug baseado APENAS na subcategoria (sem a categoria).

    Valor histórico da coluna ``subcategoria`` da tabela aninhada
    ``recommendations``. Subcategorias homônimas colapsam neste slug e
    **colidem na mesma partição** (última execução do dia vence).

    ATENÇÃO: não usar direto para gravar a aninhada — use
    :func:`nested_subcategoria`, que aplica as exceções de slug legado.
    """
    return _slugify(subcategory_name)


# Exceções onde o slug legado esperado pelo downstream difere do simple_slug.
# Validado 1:1 contra o dicionário SUBCATEGORY_NAMES histórico do consumidor:
#   - "Creme para Assaduras": o slug legado abrevia (sem "para").
#   - hífen/vírgula: a convenção legada MANTÉM esses caracteres.
LEGACY_NESTED_SLUG_OVERRIDES = {
    "Creme para Assaduras": "creme_assaduras",
    "Bombinha Tira-Leite": "bombinha_tira-leite",
    "Cama, Mesa e Banho": "cama,_mesa_e_banho",
    "Creme para Pentear e Leave-in": "creme_para_pentear_e_leave-in",
    "Pré-treinos": "pre-treinos",
    "Pós-Barba": "pos-barba",
    "Roll-on": "roll-on",
}


def category_slug(category_name: str) -> str:
    """Slug ASCII da categoria (ex.: 'Troca de Fralda' -> 'troca_de_fralda').

    Coluna ``categoria`` da ``recommendations_flat``; junto com
    ``subcategoria`` (slug legado) desambigua subcategorias homônimas.
    """
    return _slugify(category_name)


def nested_subcategoria(subcategory_name: str) -> str:
    """Slug legado da coluna ``subcategoria`` (contrato do downstream).

    ``simple_slug`` do ``subcategory_name``, com as exceções de
    :data:`LEGACY_NESTED_SLUG_OVERRIDES`. Deve ser a ÚNICA fonte do valor
    gravado na coluna ``subcategoria`` das saídas.
    """
    return LEGACY_NESTED_SLUG_OVERRIDES.get(
        subcategory_name, simple_slug(subcategory_name)
    )
