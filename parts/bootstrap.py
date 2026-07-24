# -*- coding: utf-8 -*-
"""Popula a tabela Delta de config por subcategoria a partir do infos.yaml."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

import yaml

from parts.config_generator import build_infos_entry_from_template
from parts.config_loader import build_config_from_infos
from parts.constants import (
    CONFIG_TABLE,
    DEFAULT_TOP_K,
    FARMA_SUBCATEGORIES_DEFAULT,
    SUBCATEGORY_NAMES,
)

logger = logging.getLogger(__name__)


def bootstrap_config_table(
    spark,
    infos_path: str,
    updated_by: str = "similis-bootstrap",
    subcategories: list = None,
):
    from pyspark.sql.types import (
        BooleanType,
        DoubleType,
        IntegerType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    with open(infos_path, "r", encoding="utf-8") as f:
        infos = yaml.safe_load(f) or {}
    list_ids: Dict[str, Any] = infos.get("list_ids") or {}

    subs = subcategories or FARMA_SUBCATEGORIES_DEFAULT
    rows = []
    now = datetime.now(timezone.utc)

    for sub in subs:
        entry = list_ids.get(sub)
        if not entry:
            # Sem curadoria no infos.yaml: baseline por template (a tabela
            # cobre TODAS as subcategorias do inventário, não só as curadas).
            if sub not in SUBCATEGORY_NAMES:
                logger.warning(
                    "Subcategoria %r ausente em infos.yaml e no inventário — ignorando.",
                    sub,
                )
                continue
            entry = build_infos_entry_from_template(sub)
        cfg = build_config_from_infos(sub, entry, top_k_default=DEFAULT_TOP_K)
        bounds_json = (
            json.dumps(list(cfg.quantity_ratio_bounds))
            if cfg.quantity_ratio_bounds is not None
            else None
        )
        for rule in cfg.rules:
            rows.append(
                {
                    "subcategoria": sub,
                    "subcategory_name": cfg.subcategory_name or None,
                    "category_name": cfg.category_name or None,
                    "attribute": rule.attribute,
                    "attribute_type": rule.attribute_type,
                    "weight": float(rule.weight),
                    "boost_factor": float(rule.boost_factor),
                    "top_k": cfg.top_k,
                    "min_score": cfg.min_score,
                    "quantity_ratio_bounds": bounds_json,
                    # Colunas novas (antes só existiam no YAML e o loader
                    # precisava completá-las eternamente do infos.yaml).
                    "quantity_kind": cfg.quantity_kind,
                    "candidate_pool_multiplier": cfg.candidate_pool_multiplier,
                    "active": True,
                    "updated_by": updated_by,
                    "updated_at": now,
                }
            )

    if not rows:
        raise RuntimeError("Nenhuma linha gerada para bootstrap.")

    schema = StructType(
        [
            StructField("subcategoria", StringType(), False),
            StructField("subcategory_name", StringType(), True),
            StructField("category_name", StringType(), True),
            StructField("attribute", StringType(), False),
            StructField("attribute_type", StringType(), False),
            StructField("weight", DoubleType(), True),
            StructField("boost_factor", DoubleType(), True),
            StructField("top_k", IntegerType(), True),
            StructField("min_score", DoubleType(), True),
            StructField("quantity_ratio_bounds", StringType(), True),
            StructField("quantity_kind", StringType(), True),
            StructField("candidate_pool_multiplier", IntegerType(), True),
            StructField("active", BooleanType(), True),
            StructField("updated_by", StringType(), True),
            StructField("updated_at", TimestampType(), True),
        ]
    )

    sdf = spark.createDataFrame(rows, schema=schema)
    (
        sdf.write.mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(CONFIG_TABLE)
    )
    logger.info("Bootstrap concluído: %d linhas em %s", len(rows), CONFIG_TABLE)
