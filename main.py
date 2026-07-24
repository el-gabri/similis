# -*- coding: utf-8 -*-
"""
Similis Farma: sugestões de produtos substitutos por similaridade semântica (BGE-M3).

Modos:
  predict             — gera recomendações e grava nas tabelas de produção
  predict_all         — idem, para FARMA_SUBCATEGORIES_DEFAULT
  predict_staging     — gera em tabelas intermediárias para validação
  predict_all_staging — todas em tabelas intermediárias para validação
  generate_config     — cria infos.generated.yaml com baseline por template
  bootstrap           — popula a tabela Delta de config a partir do infos.yaml

Invocação: flags (``--mode predict --subcategories fraldas,talco --top-k 50``)
ou posicional legada (``main.py '["fraldas"]' predict 50`` — contrato do
Databricks Asset Bundle atual; remover o shim quando o bundle migrar).
"""
from __future__ import annotations

import argparse
import ast
import gc
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import yaml

_SIMILIS_ROOT = os.path.dirname(os.path.abspath(__file__))
if _SIMILIS_ROOT not in sys.path:
    sys.path.insert(0, _SIMILIS_ROOT)

from parts.bootstrap import bootstrap_config_table  # noqa: E402
from parts.config_loader import ConfigLoader  # noqa: E402
from parts.constants import (  # noqa: E402
    DEFAULT_TOP_K,
    EXCLUDED_SUBCATEGORIES,
    FARMA_SUBCATEGORIES_DEFAULT,
    RECOMMENDATIONS_FLAT_STAGING_TABLE,
    RECOMMENDATIONS_FLAT_TABLE,
    RECOMMENDATIONS_STAGING_TABLE,
    RECOMMENDATIONS_TABLE,
    nested_subcategoria,
)
from parts.config_generator import (  # noqa: E402
    generate_infos_entries,
    merge_generated_entries,
    write_infos_yaml,
)
from parts.data_loader import load_catalog  # noqa: E402
from parts.embedder import BgeM3Embedder  # noqa: E402
from parts.normalizer import normalize_dataframe  # noqa: E402
from parts.ranker import recommend  # noqa: E402
from parts.writer import write_recommendations  # noqa: E402

logger = logging.getLogger("similis")

INFOS_PATH = os.path.join(_SIMILIS_ROOT, "infos.yaml")
GENERATED_INFOS_PATH = os.path.join(_SIMILIS_ROOT, "infos.generated.yaml")

MODE_PREDICT = "predict"
MODE_PREDICT_STAGING = "predict_staging"
MODE_PREDICT_ALL = "predict_all"
MODE_PREDICT_ALL_STAGING = "predict_all_staging"
MODE_GENERATE_CONFIG = "generate_config"
MODE_BOOTSTRAP = "bootstrap"

PREDICT_MODES = {
    MODE_PREDICT,
    MODE_PREDICT_STAGING,
    MODE_PREDICT_ALL,
    MODE_PREDICT_ALL_STAGING,
}
STAGING_MODES = {MODE_PREDICT_STAGING, MODE_PREDICT_ALL_STAGING}
VALID_MODES = PREDICT_MODES | {MODE_GENERATE_CONFIG, MODE_BOOTSTRAP}


@dataclass(frozen=True)
class JobArgs:
    subcategories: list
    mode: str
    top_k_default: int


def parse_job_arg(arg, default=None):
    if arg is None:
        return default
    arg = str(arg).strip()
    if arg.startswith('"') and arg.endswith('"'):
        arg = arg[1:-1]
    try:
        return ast.literal_eval(arg)
    except (SyntaxError, ValueError):
        return arg


def _parse_subcategories(raw, default):
    parsed = parse_job_arg(raw, default)
    if isinstance(parsed, str):
        # aceita CSV ("fraldas,talco") além de string única
        parsed = [p.strip() for p in parsed.split(",") if p.strip()]
    return list(parsed) if parsed else list(default)


def parse_cli_args(args: list) -> JobArgs:
    """Parse dos argumentos: flags (argparse) ou posicional legado.

    Posicional (contrato do DAB atual): ``main.py <subcategories> <mode> <top_k>``.
    Flags: ``--subcategories``, ``--mode``, ``--top-k``.
    """
    argv = list(args[1:])
    if any(str(a).startswith("--") for a in argv):
        parser = argparse.ArgumentParser(prog="similis", description=__doc__)
        parser.add_argument(
            "--subcategories",
            default=None,
            help='Lista JSON, CSV ou slug único (default: todas de FARMA_SUBCATEGORIES_DEFAULT)',
        )
        parser.add_argument("--mode", default=MODE_PREDICT, choices=sorted(VALID_MODES))
        parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, dest="top_k")
        ns = parser.parse_args(argv)
        return JobArgs(
            subcategories=_parse_subcategories(ns.subcategories, FARMA_SUBCATEGORIES_DEFAULT),
            mode=ns.mode.strip().lower(),
            top_k_default=int(ns.top_k),
        )

    # ---- shim posicional legado -------------------------------------------
    subcategories_raw = argv[0] if len(argv) > 0 else str(FARMA_SUBCATEGORIES_DEFAULT)
    mode_raw = argv[1] if len(argv) > 1 else MODE_PREDICT
    top_k_raw = argv[2] if len(argv) > 2 else str(DEFAULT_TOP_K)

    subcategories = parse_job_arg(subcategories_raw, FARMA_SUBCATEGORIES_DEFAULT)
    if isinstance(subcategories, str):
        subcategories = [subcategories]
    mode = str(parse_job_arg(mode_raw, MODE_PREDICT)).strip().lower()
    top_k_default = int(parse_job_arg(top_k_raw, DEFAULT_TOP_K))
    return JobArgs(subcategories=subcategories, mode=mode, top_k_default=top_k_default)


def assert_subcategory_allowed(subcategory: str):
    if subcategory.lower() in EXCLUDED_SUBCATEGORIES:
        raise ValueError(
            f"Subcategoria '{subcategory}' não é permitida no Similis Farma "
            f"(excluídas: {sorted(EXCLUDED_SUBCATEGORIES)})."
        )


def _output_tables(output_target: str = "prod") -> tuple:
    if output_target == "staging":
        return RECOMMENDATIONS_STAGING_TABLE, RECOMMENDATIONS_FLAT_STAGING_TABLE
    if output_target == "prod":
        return RECOMMENDATIONS_TABLE, RECOMMENDATIONS_FLAT_TABLE
    raise ValueError(f"output_target inválido: {output_target!r} (use prod ou staging)")


def _output_target_for_mode(mode: str) -> str:
    return "staging" if mode in STAGING_MODES else "prod"


def _subcategories_for_mode(mode: str, subcategories: list) -> list:
    if mode in {MODE_PREDICT_ALL, MODE_PREDICT_ALL_STAGING}:
        return subcategories or FARMA_SUBCATEGORIES_DEFAULT
    return subcategories


def create_spark_session():
    try:
        from pyspark.sql import SparkSession

        return (
            SparkSession.builder.config("spark.sql.shuffle.partitions", "200")
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
            .config("spark.sql.adaptive.skewJoin.enabled", "true")
            .config("spark.sql.execution.arrow.pyspark.enabled", "true")
            .config("spark.sql.execution.arrow.maxRecordsPerBatch", "10000")
            .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
            .getOrCreate()
        )
    except Exception as exc:
        msg = str(exc)
        if (
            isinstance(exc, ImportError)
            or "JAVA_GATEWAY_EXITED" in msg
            or "Java gateway" in msg
            or "Java Runtime" in msg
        ):
            raise RuntimeError(
                "Não foi possível iniciar Spark localmente. Os modos predict/bootstrap "
                "devem rodar no Databricks (ou em uma máquina com Java/Spark e acesso "
                "às tabelas Delta). Localmente, use apenas mode=generate_config."
            ) from exc
        raise


def run_predict(
    spark,
    subcategory: str,
    top_k_default: int,
    output_target: str = "prod",
    loader: ConfigLoader = None,
    embedder: BgeM3Embedder = None,
    run_date: str = None,
):
    assert_subcategory_allowed(subcategory)
    loader = loader or ConfigLoader(spark, INFOS_PATH, top_k_default=top_k_default)
    embedder = embedder or BgeM3Embedder()
    config = loader.get(subcategory)
    recommendations_table, recommendations_flat_table = _output_tables(output_target)

    if not config.subcategory_name:
        raise RuntimeError(
            f"Subcategoria {subcategory!r} sem 'subcategory_name' (preencha em "
            f"infos.yaml ou na tabela {config.source})."
        )

    logger.info(
        "Subcategoria slug=%r subcategory_name=%r category_name=%r "
        "quantity_ratio_bounds=%s output_target=%r",
        subcategory,
        config.subcategory_name,
        config.category_name,
        config.quantity_ratio_bounds,
        output_target,
    )

    df = load_catalog(spark, config.subcategory_name, config)
    if df.empty:
        logger.warning("Catálogo vazio para %s; nada a recomendar.", subcategory)
        return

    logger.info("Catálogo carregado: %d EANs únicos.", len(df))

    df = normalize_dataframe(df, config)
    embeddings = embedder.encode_dataframe(df, subcategory)

    recs = recommend(
        df,
        embeddings,
        config,
        quantity_ratio_bounds=config.quantity_ratio_bounds,
    )

    name_by_ean = df.set_index("EAN")["PRODUCT_NAME"].to_dict()
    write_recommendations(
        spark,
        recs,
        subcategory,
        config.config_hash,
        name_by_ean=name_by_ean,
        recommendations_table=recommendations_table,
        recommendations_flat_table=recommendations_flat_table,
        category_name=config.category_name,
        run_date=run_date,
        # Aninhada mantém o slug legado histórico (subcategory_name); a flat
        # segue com o slug legado + coluna categoria.
        subcategoria_nested=nested_subcategoria(config.subcategory_name),
    )
    gc.collect()


def run_many(spark, subcategories: list, top_k_default: int, output_target: str = "prod"):
    loader = ConfigLoader(spark, INFOS_PATH, top_k_default=top_k_default)
    embedder = BgeM3Embedder()
    # Data da rodada computada UMA vez: uma execução longa (várias subcategorias)
    # pode atravessar a meia-noite UTC; sem isso, as primeiras subcategorias
    # cairiam numa partição ``date`` e as últimas em outra.
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for subcategory in subcategories:
        logger.info("=== Similis predict: %s ===", subcategory)
        run_predict(
            spark,
            subcategory,
            top_k_default,
            output_target=output_target,
            loader=loader,
            embedder=embedder,
            run_date=run_date,
        )


def run_bootstrap(spark, subcategories: list):
    subs = [s for s in subcategories if s.lower() not in EXCLUDED_SUBCATEGORIES]
    bootstrap_config_table(spark, INFOS_PATH, subcategories=subs)


def run_generate_config(subcategories: list, output_path: str = GENERATED_INFOS_PATH):
    subs = [s for s in subcategories if s.lower() not in EXCLUDED_SUBCATEGORIES]
    with open(INFOS_PATH, "r", encoding="utf-8") as f:
        current_infos = yaml.safe_load(f) or {}

    generated = generate_infos_entries(subs)
    merged = merge_generated_entries(
        current_infos,
        generated,
        overwrite_existing=False,
    )
    write_infos_yaml(output_path, merged)

    preserved = sum(1 for slug in generated if slug in (current_infos.get("list_ids") or {}))
    created = len(generated) - preserved
    by_template = {}
    for entry in generated.values():
        template = entry.get("template", "unknown")
        by_template[template] = by_template.get(template, 0) + 1

    logger.info("Config gerada em: %s", output_path)
    logger.info("Subcategorias elegíveis: %d", len(generated))
    logger.info("Entradas preservadas do infos.yaml: %d", preserved)
    logger.info("Entradas novas por template: %d", created)
    logger.info("Distribuição por template: %s", dict(sorted(by_template.items())))


def main(argv: list = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    job_args = parse_cli_args(argv if argv is not None else sys.argv)

    logger.info(
        "subcategories=%s mode=%s top_k=%s",
        job_args.subcategories,
        job_args.mode,
        job_args.top_k_default,
    )

    if job_args.mode == MODE_GENERATE_CONFIG:
        run_generate_config(job_args.subcategories or FARMA_SUBCATEGORIES_DEFAULT)
        return 0

    spark = create_spark_session()

    if job_args.mode == MODE_BOOTSTRAP:
        # Bootstrap sempre repovoa todas as subcategorias Farma (evita
        # overwrite parcial no for_each).
        run_bootstrap(spark, FARMA_SUBCATEGORIES_DEFAULT)
    elif job_args.mode in PREDICT_MODES:
        run_many(
            spark,
            _subcategories_for_mode(job_args.mode, job_args.subcategories),
            job_args.top_k_default,
            output_target=_output_target_for_mode(job_args.mode),
        )
    else:
        raise ValueError(
            f"Modo desconhecido: {job_args.mode!r} "
            f"(use {', '.join(sorted(VALID_MODES))})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
