# -*- coding: utf-8 -*-
"""Resolução do universo de SKUs por subcategoria via business_categorization.

Substitui a antiga resolução por ``dicionarios_rag_de_para``. Agora o universo
vem direto de ``products_categorization`` (filtrado por business_type, departamentos
permitidos e a lista fixa de category_ids) e é cruzado com ``skus_products``.
"""
from __future__ import annotations

from parts.constants import (
    ALLOWED_CATEGORY_IDS,
    DEFAULT_BUSINESS_TYPE,
    EXCLUDED_DEPARTMENTS,
    PRODUCTS_CATEGORIZATION_TABLE,
    SKUS_PRODUCTS_TABLE,
)

_PHARMACY_PATH = "business_categorization.pharmacy"


def get_universe_skus(
    spark,
    subcategory_name: str,
    category_name: str = None,
    business_type: str = DEFAULT_BUSINESS_TYPE,
):
    """Retorna SKUs da subcategoria Farma (snapshot ``current_date``).

    Replica a CTE ``categorias`` da query oficial do universo:

      - ``business_type_name = 'Farmácia'``
      - ``department_name`` fora de :data:`EXCLUDED_DEPARTMENTS`
      - ``category_id`` em :data:`ALLOWED_CATEGORY_IDS`
      - ``subcategory_name`` igual ao informado
      - ``category_name`` igual ao informado (quando fornecido) — desambigua
        subcategorias homônimas que aparecem sob categorias diferentes
        (ex.: "Absorvente com Abas" em "Absorvente Diurno" vs "Noturno").
      - ``skus_products.dt = current_date()``
    """
    from pyspark.sql import functions as F

    cat = spark.table(PRODUCTS_CATEGORIZATION_TABLE)
    prod = spark.table(SKUS_PRODUCTS_TABLE).where(F.col("dt") == F.current_date())

    excluded = list(EXCLUDED_DEPARTMENTS)
    allowed = list(ALLOWED_CATEGORY_IDS)

    filtered = (
        cat.where(F.col(f"{_PHARMACY_PATH}.business_type_name") == F.lit(business_type))
        .where(~F.col(f"{_PHARMACY_PATH}.department_name").isin(excluded))
        .where(F.col(f"{_PHARMACY_PATH}.category_id").isin(allowed))
        .where(F.col(f"{_PHARMACY_PATH}.subcategory_name") == F.lit(subcategory_name))
    )
    if category_name:
        filtered = filtered.where(
            F.col(f"{_PHARMACY_PATH}.category_name") == F.lit(category_name)
        )
    filtered = (
        filtered.select(
            F.col(f"{_PHARMACY_PATH}.department_name").alias("department_name"),
            F.col(f"{_PHARMACY_PATH}.category_name").alias("category_name"),
            F.col(f"{_PHARMACY_PATH}.subcategory_name").alias("subcategory_name"),
            F.col("product_name"),
            F.col("product_ean"),
            F.col("product_id"),
        )
        .distinct()
    )

    universe = (
        filtered.join(prod, "product_id", "inner")
        .select(
            "department_name",
            "category_name",
            "subcategory_name",
            "product_name",
            "product_ean",
            "product_id",
            "sku_id",
        )
        .dropDuplicates(["sku_id"])
    )
    return universe
