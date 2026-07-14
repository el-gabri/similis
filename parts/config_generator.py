# -*- coding: utf-8 -*-
"""Geração de configurações baseline a partir de templates."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping, Optional

import yaml

from parts.constants import (
    FARMA_SUBCATEGORIES_DEFAULT,
    SUBCATEGORY_CATEGORIES,
    SUBCATEGORY_NAMES,
)
from parts.subcategory_policy import choose_template


def build_infos_entry_from_template(
    slug: str,
    subcategory_name: Optional[str] = None,
    category_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Gera uma entrada `infos.yaml` para uma subcategoria."""
    literal_name = (subcategory_name or SUBCATEGORY_NAMES.get(slug) or "").strip()
    literal_category = (category_name or SUBCATEGORY_CATEGORIES.get(slug) or "").strip()
    template = choose_template(slug, literal_name)

    entry: Dict[str, Any] = {
        "subcategory_name": literal_name,
        "category_name": literal_category,
        "top_k": template.top_k,
        "min_score": template.min_score,
        "quantity_kind": template.quantity_kind,
        "template": template.name,
        "risk": template.risk,
        "list_columns": list(template.list_columns),
        "config_overrides": deepcopy(template.config_overrides),
    }
    if template.quantity_ratio_bounds is not None:
        entry["quantity_ratio_bounds"] = list(template.quantity_ratio_bounds)
    # Omitido quando 1 (default): só polui o YAML e o hash.
    if template.candidate_pool_multiplier != 1:
        entry["candidate_pool_multiplier"] = template.candidate_pool_multiplier
    return entry


def generate_infos_entries(
    subcategories: Optional[Iterable[str]] = None,
    subcategory_names: Optional[Mapping[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Gera entradas baseline para os slugs informados."""
    names = dict(subcategory_names or SUBCATEGORY_NAMES)
    subs = list(subcategories or FARMA_SUBCATEGORIES_DEFAULT)
    return {
        slug: build_infos_entry_from_template(slug, names.get(slug))
        for slug in subs
        if names.get(slug)
    }


def merge_generated_entries(
    current_infos: Mapping[str, Any],
    generated_entries: Mapping[str, Dict[str, Any]],
    overwrite_existing: bool = False,
) -> Dict[str, Any]:
    """Mescla configs geradas em um payload de `infos.yaml`.

    Por padrão preserva entradas já existentes, que representam curadoria manual.
    """
    out: Dict[str, Any] = deepcopy(dict(current_infos or {}))
    list_ids = deepcopy(out.get("list_ids") or {})
    for slug, entry in generated_entries.items():
        if overwrite_existing or slug not in list_ids:
            list_ids[slug] = deepcopy(entry)
    out["list_ids"] = list_ids
    return out


def write_infos_yaml(path: str, infos: Mapping[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            dict(infos),
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
