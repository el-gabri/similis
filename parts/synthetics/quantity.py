# -*- coding: utf-8 -*-
"""Sintéticos de quantidade: ``quantity_norm`` e ``metragem_norm``."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from parts.synthetics.base import register, resolve_column
from parts.units import convert_unit, parse_mass_volume, parse_metragem, parse_pack_size


@register("quantity_norm", required_metadata_keys={"quantity", "quantityUnit"})
def compute_quantity_norm(df: pd.DataFrame, config) -> pd.Series:
    """Quantidade canônica ("1,5 kg" -> "1500 g", "96 un").

    ``quantity_kind="count"`` (default): (1) contagem extraída do PRODUCT_NAME
    via ``parse_pack_size`` (confiável; o metadata de fraldas vem duplicado/
    inflado); (2) fallback: parte numérica de ``quantity`` do metadata.

    ``quantity_kind="mass"`` (leite em pó, cremes...): (1) massa/volume do
    NOME via ``parse_mass_volume`` (o metadata vem inflado/inconsistente
    nesse universo); (2) fallback: ``quantity`` + ``quantityUnit`` normalizados.
    """
    quantity_kind = getattr(config, "quantity_kind", "count")
    qcol = resolve_column(df, "quantity")
    ucol = resolve_column(df, "quantityUnit")

    def _qnorm(row):
        name = row.get("PRODUCT_NAME", "") or ""
        if quantity_kind == "mass":
            mv = parse_mass_volume(name)
            if mv:
                return mv
            if qcol is not None:
                q = row.get(qcol, "")
                if q is not None and not (isinstance(q, float) and pd.isna(q)):
                    num = re.search(r"\d+\.?\d*", str(q))
                    unit = ""
                    if ucol is not None:
                        u = row.get(ucol, "") or ""
                        um = re.search(r"[a-zA-Z]+", str(u))
                        unit = um.group(0) if um else ""
                    if num:
                        mv = convert_unit(f"{num.group(0)}{unit or 'g'}")
                        if mv != "not available":
                            return mv
            return ""
        total = parse_pack_size(name)["total"]
        if total is not None and not (isinstance(total, float) and pd.isna(total)):
            return convert_unit(f"{int(total)} un")
        # FALLBACK do metadata — agora UNIT-AWARE [bge-m3-v1.7]:
        # o fallback antigo cunhava sempre "N un", então um produto de 200ml
        # sem token de contagem no nome virava "200 un" e o filtro de
        # quantidade comparava ml com g como se fossem a mesma unidade
        # (53 subcategorias reprovadas no judge por isso). Agora o
        # quantityUnit é respeitado: ml/g/l -> forma canônica de massa/volume;
        # unidade de contagem ou ausente -> "N un" (comportamento antigo).
        if qcol is not None:
            q = row.get(qcol, "")
            if q is not None and not (isinstance(q, float) and pd.isna(q)):
                m = re.search(r"\d+\.?\d*", str(q))
                if m:
                    unit = ""
                    if ucol is not None:
                        u = row.get(ucol, "") or ""
                        um = re.search(r"[a-zA-Z]+", str(u))
                        unit = (um.group(0) if um else "").lower()
                    if unit and unit not in ("un", "und", "unds", "uni", "unid",
                                             "unidade", "unidades", "pc", "pcs"):
                        mv = convert_unit(f"{m.group(0)}{unit}")
                        if mv != "not available":
                            return mv
                    return convert_unit(f"{m.group(0)} un")
        return ""

    return df.apply(_qnorm, axis=1)


@register("metragem_norm")
def compute_metragem_norm(df: pd.DataFrame, config) -> pd.Series:
    """Metros por rolo ('30 m') extraídos do PRODUCT_NAME, ou ''."""

    def _one(name):
        mt = parse_metragem(name or "")
        if mt is None or (isinstance(mt, float) and np.isnan(mt)):
            return ""
        return f"{int(round(mt))} m"

    return df["PRODUCT_NAME"].map(_one)
