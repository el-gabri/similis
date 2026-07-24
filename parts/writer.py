# -*- coding: utf-8 -*-
"""Persistência das recomendações em Delta (tabela aninhada + tabela flat).

``prepare_recommendations_output`` é Spark-free (testável localmente); só as
funções ``write_*`` importam pyspark (lazy) e persistem.

CONTRATO: os schemas das duas tabelas são consumidos por downstream em
produção — NÃO adicionar/remover colunas nem chaves no JSON de ``sugestoes``
sem alinhamento prévio.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import pandas as pd

from parts.constants import (
    MODEL_VERSION,
    RECOMMENDATIONS_FLAT_TABLE,
    RECOMMENDATIONS_TABLE,
    category_slug,
)

logger = logging.getLogger(__name__)

# (nome, tipo spark) — fonte única das colunas; o StructType é montado
# lazy em _spark_schema para manter este módulo importável sem pyspark.
FLAT_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("ean_origem", "string"),
    ("product_name_origem", "string"),
    ("ean_sugestao", "string"),
    ("product_name_sugestao", "string"),
    ("rank", "int"),
    ("relevance", "double"),
    ("n_sugestoes", "int"),
    ("subcategoria", "string"),
    ("categoria", "string"),
    ("model_version", "string"),
    ("config_hash", "string"),
    ("date", "string"),
)

RECOMMENDATIONS_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("ean_origem", "string"),
    ("product_name_origem", "string"),
    ("subcategoria", "string"),
    ("sugestoes", "string"),
    ("n_sugestoes", "int"),
    ("model_version", "string"),
    ("config_hash", "string"),
    ("date", "string"),
)

FLAT_COLUMN_NAMES = tuple(name for name, _ in FLAT_COLUMNS)
RECOMMENDATIONS_COLUMN_NAMES = tuple(name for name, _ in RECOMMENDATIONS_COLUMNS)


def _spark_schema(columns: Tuple[Tuple[str, str], ...]):
    from pyspark.sql.types import (
        DoubleType,
        IntegerType,
        StringType,
        StructField,
        StructType,
    )

    types = {"string": StringType(), "int": IntegerType(), "double": DoubleType()}
    return StructType([StructField(n, types[t], True) for n, t in columns])


def _as_suggestion_list(sugs) -> List[dict]:
    """Lista de dicts a partir de ``sugestoes`` (lista nativa ou JSON string)."""
    if sugs is None:
        return []
    if isinstance(sugs, str):
        try:
            sugs = json.loads(sugs)
        except (TypeError, ValueError):
            return []
    return list(sugs) if isinstance(sugs, (list, tuple)) else []


def explode_recommendations(out: pd.DataFrame) -> pd.DataFrame:
    """Versão flat: 1 linha por par (ean_origem, ean_sugestao), em ordem de rank.

    EANs sem sugestão não geram linha — seguem auditáveis na aninhada via
    ``n_sugestoes = 0``.
    """
    rows = []
    for rec in out.itertuples(index=False):
        for s in _as_suggestion_list(rec.sugestoes):
            rows.append(
                {
                    "ean_origem": rec.ean_origem,
                    "product_name_origem": rec.product_name_origem,
                    "ean_sugestao": s.get("ean"),
                    "product_name_sugestao": s.get("product_name"),
                    "rank": int(s["rank"]) if s.get("rank") is not None else None,
                    "relevance": float(s["relevance"]) if s.get("relevance") is not None else None,
                    "n_sugestoes": rec.n_sugestoes,
                    "subcategoria": rec.subcategoria,
                    "categoria": getattr(rec, "categoria", None),
                    "model_version": rec.model_version,
                    "config_hash": rec.config_hash,
                    "date": rec.date,
                }
            )
    flat = pd.DataFrame(rows, columns=list(FLAT_COLUMN_NAMES))
    if not flat.empty:
        flat = flat.sort_values(["ean_origem", "rank"]).reset_index(drop=True)
    return flat


def prepare_recommendations_output(
    recs_df: pd.DataFrame,
    subcategoria: str,
    config_hash: str,
    model_version: str = MODEL_VERSION,
    run_date: Optional[str] = None,
    name_by_ean: Optional[dict] = None,
    write_flat: bool = True,
    category_name: str = "",
    subcategoria_nested: Optional[str] = None,
) -> tuple:
    """Prepara os DataFrames aninhado e flat sem tocar no Spark.

    Identidade nas saídas:
      - ``subcategoria`` (ambas): slug legado (``subcategoria_nested``; quando
        ``None`` cai em ``subcategoria``). Ex.: ``creme_assaduras``.
      - ``categoria`` (**só na flat**): slug derivado de ``category_name``.
        O par ``(subcategoria, categoria)`` desambigua homônimas.
    O JSON de ``sugestoes`` carrega exatamente {ean, relevance, rank,
    product_name} — chaves extras do ranker são descartadas aqui para
    proteger o contrato do downstream.
    """
    # UTC explícito: alinha a partição ``date`` ao ``current_date()`` dos
    # snapshots de entrada e evita depender do fuso do driver. O chamador
    # (main.run_many) já computa a data UMA vez e a repassa — este fallback só
    # vale para uso interativo/testes.
    run_date = run_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = recs_df.copy()
    out["subcategoria"] = subcategoria_nested or subcategoria
    # Slug da categoria: só a flat consome; a aninhada é recortada por
    # RECOMMENDATIONS_COLUMN_NAMES no final desta função (sem categoria).
    out["categoria"] = category_slug(category_name)
    out["n_sugestoes"] = out["sugestoes"].apply(lambda s: len(_as_suggestion_list(s)))

    name_by_ean = name_by_ean or {}

    _CONTRACT_KEYS = ("ean", "relevance", "rank")

    def _enrich(sugs):
        items = _as_suggestion_list(sugs)
        return [
            {
                **{k: s.get(k) for k in _CONTRACT_KEYS},
                "product_name": s.get("product_name") or name_by_ean.get(s.get("ean")),
            }
            for s in items
        ]

    out["sugestoes"] = out["sugestoes"].apply(_enrich)
    out["product_name_origem"] = out["ean_origem"].map(lambda e: name_by_ean.get(e))
    out["model_version"] = model_version
    out["config_hash"] = config_hash
    out["date"] = run_date

    flat = explode_recommendations(out) if write_flat else None

    out["sugestoes"] = out["sugestoes"].apply(
        lambda x: json.dumps(x, ensure_ascii=False)
    )
    out = out[list(RECOMMENDATIONS_COLUMN_NAMES)]
    return out, flat, run_date


def _write_partitioned_table(
    spark,
    pdf: pd.DataFrame,
    columns: Tuple[Tuple[str, str], ...],
    table_name: str,
    partition_cols: tuple = ("date", "subcategoria"),
) -> None:
    sdf = spark.createDataFrame(pdf, schema=_spark_schema(columns))
    (
        sdf.write.mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        # mergeSchema mantido por ora: remover exige garantir que as tabelas
        # de prod/staging já contenham todas as colunas (README §13).
        .option("mergeSchema", "true")
        .partitionBy(*partition_cols)
        .saveAsTable(table_name)
    )


def write_recommendations(
    spark,
    recs_df: pd.DataFrame,
    subcategoria: str,
    config_hash: str,
    model_version: str = MODEL_VERSION,
    run_date: Optional[str] = None,
    name_by_ean: Optional[dict] = None,
    write_flat: bool = True,
    recommendations_table: str = RECOMMENDATIONS_TABLE,
    recommendations_flat_table: str = RECOMMENDATIONS_FLAT_TABLE,
    category_name: str = "",
    subcategoria_nested: Optional[str] = None,
):
    if recs_df.empty:
        logger.info("Nenhuma recomendação para gravar (%s).", subcategoria)
        return

    out, flat, run_date = prepare_recommendations_output(
        recs_df=recs_df,
        subcategoria=subcategoria,
        config_hash=config_hash,
        model_version=model_version,
        run_date=run_date,
        name_by_ean=name_by_ean,
        write_flat=write_flat,
        category_name=category_name,
        subcategoria_nested=subcategoria_nested,
    )

    nested_slug = subcategoria_nested or subcategoria
    _write_partitioned_table(spark, out, RECOMMENDATIONS_COLUMNS, recommendations_table)
    logger.info(
        "Gravado %d linhas em %s (date=%s, subcategoria=%s)",
        len(out), recommendations_table, run_date, nested_slug,
    )

    if write_flat:
        write_recommendations_flat(
            spark,
            flat,
            subcategoria,
            run_date,
            recommendations_flat_table=recommendations_flat_table,
        )


def write_recommendations_flat(
    spark,
    flat: pd.DataFrame,
    subcategoria: str,
    run_date: str,
    recommendations_flat_table: str = RECOMMENDATIONS_FLAT_TABLE,
):
    """Grava a flat, particionada por (date, subcategoria, categoria).

    A ``categoria`` entra na chave de partição porque a ``subcategoria`` da
    flat é o slug legado (sem categoria) — sem ela, homônimas colidiriam.
    """
    if flat is None or flat.empty:
        logger.info(
            "Nenhum par origem→sugestão para gravar em %s (%s).",
            recommendations_flat_table, subcategoria,
        )
        return

    flat = flat[list(FLAT_COLUMN_NAMES)]
    _write_partitioned_table(
        spark,
        flat,
        FLAT_COLUMNS,
        recommendations_flat_table,
        partition_cols=("date", "subcategoria", "categoria"),
    )
    logger.info(
        "Gravado %d pares em %s (date=%s, subcategoria=%s)",
        len(flat), recommendations_flat_table, run_date, subcategoria,
    )
