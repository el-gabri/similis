# -*- coding: utf-8 -*-
"""Carrega catálogo Farma com atributos pivotados a partir do ``skus_metadata``."""
from __future__ import annotations

import logging
from typing import List

import pandas as pd

from parts.config_loader import SubcategoryConfig
from parts.constants import (
    SKUS_METADATA_TABLE,
    SKUS_TABLE,
)
from parts.subcategory_ids import get_universe_skus
from parts.synthetics import REGISTRY, SYNTHETIC_ATTRIBUTES  # noqa: F401 (re-export)

logger = logging.getLogger(__name__)

# Colunas que já vêm do datasheet base (``skus``), NÃO do ``skus_metadata`` —
# nunca pivotar: pivotá-las duplicaria a coluna no join (``base`` já traz
# ``product_description`` de ``skus.description``) e um df com coluna duplicada
# quebra o normalizer (``df[col]`` vira DataFrame). No código antigo esse papel
# era cumprido por ``product_description`` estar no SYNTHETIC_ATTRIBUTES manual.
BASE_DATASHEET_COLUMNS = frozenset({"product_description"})


def _required_metadata_keys(config: SubcategoryConfig) -> List[str]:
    """Keys do ``skus_metadata`` necessárias para a config.

    Keys de regras não-sintéticas + as ``required_metadata_keys`` declaradas
    no registro de sintéticos (antes eram conjuntos especiais mantidos à mão
    aqui, que precisavam bater com o normalizer). Exclui sintéticos e colunas
    do datasheet base.
    """
    keys = {
        a
        for a in config.all_attributes
        if a not in SYNTHETIC_ATTRIBUTES and a not in BASE_DATASHEET_COLUMNS
    }
    for attr in config.all_attributes:
        spec = REGISTRY.get(attr)
        if spec is not None:
            keys.update(spec.required_metadata_keys)
    return sorted(keys)


def _build_base_skus(spark, subcategory_name: str, category_name: str = None):
    """SKUs do universo da subcategoria + colunas básicas do datasheet."""
    from pyspark.sql import functions as F

    skus = (
        spark.table(SKUS_TABLE)
        .where(F.col("dt") == F.current_date())
        .select(
            F.col("sku_id"),
            F.col("name").alias("product_name_sku"),
            F.col("description").alias("product_description"),
            F.col("updated_at"),
        )
    )
    universe = get_universe_skus(spark, subcategory_name, category_name=category_name)
    return universe.join(skus, "sku_id", "inner")


def _build_pivot(spark, sku_ids_df, keys: List[str]):
    """Pivot do ``skus_metadata`` restrito aos SKUs do universo e às keys."""
    from pyspark.sql import functions as F

    if not keys:
        return sku_ids_df.select("sku_id").distinct().withColumn(
            "_placeholder", F.lit(None).cast("string")
        ).drop("_placeholder")

    meta = (
        spark.table(SKUS_METADATA_TABLE)
        .where(F.col("dt") == F.current_date())
        .where(F.col("key").isin(keys))
    )

    meta_in_universe = meta.join(
        sku_ids_df.select("sku_id").distinct(), "sku_id", "inner"
    )

    pivoted = (
        meta_in_universe.groupBy("sku_id")
        .pivot("key", keys)
        .agg(F.first("value", ignorenulls=True))
    )
    return pivoted


def load_catalog(
    spark,
    subcategory_name: str,
    config: SubcategoryConfig,
) -> pd.DataFrame:
    """Catálogo Farma para a subcategoria, com atributos pivotados.

    Output (pandas DataFrame):
      sku_id, product_id, product_ean, EAN, PRODUCT_NAME, product_description,
      department_name, category_name, subcategory_name, updated_at,
      + uma coluna por atributo configurado (valor textual cru).
    """
    if not subcategory_name:
        raise ValueError("subcategory_name obrigatório (ex.: 'Shampoo Infantil').")

    base = _build_base_skus(spark, subcategory_name, category_name=config.category_name)
    keys = _required_metadata_keys(config)
    pivoted = _build_pivot(spark, base, keys)

    full = base.join(pivoted, "sku_id", "left")

    pdf: pd.DataFrame = full.toPandas()
    if pdf.empty:
        return pdf

    pdf.columns = [str(c) for c in pdf.columns]
    pdf["EAN"] = pdf["product_ean"].astype(str)

    # --- Sanidade do EAN -------------------------------------------------
    # Descarta códigos internos que vazam no product_ean (ex.: 'SM00200344688').
    # Proposta mais geral (validação GTIN: \d{8}|\d{12,14}) pendente de
    # validação de cobertura em produção antes de ativar.
    ean_invalido = pdf["EAN"].str.contains("SM", na=False)
    n_drop = int(ean_invalido.sum())
    if n_drop:
        exemplos = pdf.loc[ean_invalido, "EAN"].head(3).tolist()
        logger.warning(
            "%d SKUs descartados por EAN inválido (ex.: %s)", n_drop, exemplos
        )
    pdf = pdf[~ean_invalido].reset_index(drop=True)
    # ---------------------------------------------------------------------

    if "product_name_sku" in pdf.columns:
        pdf["PRODUCT_NAME"] = pdf["product_name"].fillna(pdf["product_name_sku"])
    else:
        pdf["PRODUCT_NAME"] = pdf["product_name"]
    pdf["product_description"] = pdf["product_description"].fillna("").astype(str)

    pdf = pdf.drop_duplicates(subset=["EAN"], keep="first").reset_index(drop=True)
    return pdf
