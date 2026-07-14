# -*- coding: utf-8 -*-
"""Similaridade FAISS por partição (hard_filter) e re-rank com soft_boost.

Reescrito para performance sem mudar resultados:
  - busca FAISS em LOTE (uma chamada por partição, não uma por origem);
  - quantidades parseadas UMA vez por linha (antes a origem era re-parseada
    a cada par) e valores de soft_boost pré-computados em arrays;
  - zero ``df.iloc`` dentro do loop de candidatos.
A aritmética por par (float Python, ``round(x, 6)``, sort estável) é a mesma
do código antigo — resultados byte-idênticos (verificado por golden fixture).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from parts.config_loader import SubcategoryConfig
from parts.units import parse_quantity as _parse_quantity  # compat: nome antigo

try:
    import faiss

    faiss.omp_set_num_threads(1)
    _HAS_FAISS = True
except ImportError:
    faiss = None
    _HAS_FAISS = False


class _NumpyFlatIPIndex:
    """Fallback quando faiss-cpu não está instalado (ex.: testes locais)."""

    def __init__(self, vectors: np.ndarray):
        self.vectors = np.ascontiguousarray(vectors.astype(np.float32))

    def search(self, query: np.ndarray, k: int):
        q = np.ascontiguousarray(query.astype(np.float32))
        scores = q @ self.vectors.T
        idx = np.argsort(-scores, axis=1)[:, :k]
        top_scores = np.take_along_axis(scores, idx, axis=1)
        return top_scores.astype(np.float32), idx.astype(np.int64)


def _build_partition_index(vecs: np.ndarray):
    vecs = np.ascontiguousarray(vecs.astype(np.float32))
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms
    if _HAS_FAISS:
        dim = vecs.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vecs)
        return index
    return _NumpyFlatIPIndex(vecs)


def _search_index(index, query: np.ndarray, k: int):
    q = np.ascontiguousarray(query.astype(np.float32))
    if _HAS_FAISS:
        faiss.normalize_L2(q)
        return index.search(q, k)
    norms = np.linalg.norm(q, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    q = q / norms
    return index.search(q, k)


def _col_name(df: pd.DataFrame, attr: str) -> Optional[str]:
    lookup = {str(c).lower(): c for c in df.columns}
    return lookup.get(str(attr).lower())


def recommend(
    df: pd.DataFrame,
    embeddings: np.ndarray,
    config: SubcategoryConfig,
    ean_col: str = "EAN",
    normalize_relevance: bool = True,
    quantity_attr: Optional[str] = "quantity_norm",
    quantity_ratio_bounds: Optional[Tuple[float, float]] = None,
) -> pd.DataFrame:
    """Recomenda substitutos por EAN origem.

    Retorna DataFrame com ``ean_origem`` e ``sugestoes`` (lista ORDENADA de
    dicts ``{"ean", "relevance", "rank"}``).

    Cálculo do score
    ----------------
    1. *Score bruto* = cosseno × produto dos ``boost_factor`` das regras
       ``soft_boost`` cujos atributos batem entre origem e candidato.
    2. ``config.min_score`` corta sobre o score pós-boost (default) ou sobre a
       similaridade pura quando ``config.min_score_basis == "raw_similarity"``.
    3. ``normalize_relevance=True`` (default): scores reescalados para [0, 1]
       dividindo pelo máximo da rodada (preserva a ordem).

    Filtro por faixa de quantidade
    ------------------------------
    ``quantity_ratio_bounds=(lo, hi)``: candidatos cuja quantidade esteja fora
    de ``[lo*origem, hi*origem]`` são descartados ANTES do boost. Compara só
    quando origem e candidato têm a MESMA unidade canônica e ambos parseiam;
    senão mantém (conservador). ``candidate_pool_multiplier`` busca mais
    vizinhos que o top-K final, reduzindo listas curtas pós-filtro.

    Dedup de produto
    ----------------
    ``config.suppress_same_product=True`` + coluna ``product_id`` no df:
    candidatos com o MESMO product_id da origem (EANs duplicados do mesmo
    cadastro) são suprimidos. Default False (comportamento histórico).
    """
    hard_attrs = [r.attribute for r in config.hard_filter_rules]
    col_map = {r.attribute: _col_name(df, r.attribute) or r.attribute for r in config.rules}
    soft_rules = config.soft_boost_rules

    df = df.reset_index(drop=True)
    eans = df[ean_col].astype(str).tolist()
    n = len(df)

    if n == 0:
        return pd.DataFrame(columns=["ean_origem", "sugestoes"])

    # ---- pré-computos por LINHA (uma vez, fora do loop de pares) ----------
    qcol = _col_name(df, quantity_attr) if quantity_attr else None
    quantities: Optional[List[Optional[Tuple[float, str]]]] = None
    if quantity_ratio_bounds is not None and qcol is not None:
        quantities = [_parse_quantity(v) for v in df[qcol].tolist()]

    soft_values: List[Tuple[float, List[str]]] = []
    for rule in soft_rules:
        col = col_map.get(rule.attribute)
        if not col or col not in df.columns:
            continue
        # NOTA: sem fillna — replica o antigo str(row.get(col)) byte a byte
        # (NaN vira "NAN", comportamento herdado).
        vals = [str(v).strip().upper() for v in df[col].tolist()]
        soft_values.append((rule.boost_factor, vals))

    product_ids: Optional[List[str]] = None
    suppress_same_product = bool(getattr(config, "suppress_same_product", False))
    pid_col = _col_name(df, "product_id")
    if suppress_same_product and pid_col is not None:
        product_ids = [str(v).strip() for v in df[pid_col].fillna("").tolist()]

    min_score_basis = str(getattr(config, "min_score_basis", "boosted") or "boosted")

    # ---- partições por hard_filter ----------------------------------------
    hard_val_cols = []
    for attr in hard_attrs:
        col = col_map.get(attr)
        if col and col in df.columns:
            # Sem fillna — mesmo motivo acima (partição de NaN = "NAN").
            hard_val_cols.append([str(v).strip().upper() for v in df[col].tolist()])
        else:
            hard_val_cols.append([""] * n)

    partition_indices: Dict[Tuple, List[int]] = {}
    row_partitions: List[Tuple] = []
    for i in range(n):
        key = tuple(vals[i] for vals in hard_val_cols)
        row_partitions.append(key)
        partition_indices.setdefault(key, []).append(i)

    top_k = config.top_k
    min_score = config.min_score
    candidate_pool_multiplier = max(
        1, int(getattr(config, "candidate_pool_multiplier", 1) or 1)
    )

    # ---- índices por partição ----------------------------------------------
    # NOTA: a busca é feita POR ORIGEM (query 1×N), não em lote — a matmul em
    # lote (M×N) usa kernels BLAS/SIMD diferentes e produz diferenças de 1 ulp
    # no score, que mudam a 6ª casa da relevance gravada (verificado no golden
    # fixture). O custo dominante era o df.iloc/re-parse por par, já eliminado.
    partition_indexes: Dict[Tuple, Any] = {}
    for key, idx_list in partition_indices.items():
        if len(idx_list) <= 1:
            continue
        partition_indexes[key] = _build_partition_index(embeddings[idx_list])

    # ---- montagem de candidatos (aritmética idêntica à versão antiga) ------
    results = []
    for orig_i in range(n):
        ean_origem = eans[orig_i]
        key = row_partitions[orig_i]
        index = partition_indexes.get(key)
        if index is None:
            results.append({"ean_origem": ean_origem, "sugestoes": []})
            continue

        idx_list = partition_indices[key]
        k_search = min(len(idx_list), (top_k * candidate_pool_multiplier) + 1)
        scores, indices = _search_index(index, embeddings[orig_i : orig_i + 1], k_search)

        qo = quantities[orig_i] if quantities is not None else None
        candidates: List[Dict[str, Any]] = []

        for local_idx, sim in zip(indices[0], scores[0]):
            if local_idx < 0:
                continue
            global_i = idx_list[local_idx]
            cand_ean = eans[global_i]
            if cand_ean == ean_origem:
                continue
            if (
                product_ids is not None
                and product_ids[global_i]
                and product_ids[global_i] == product_ids[orig_i]
            ):
                continue

            relevance = float(sim)

            # filtro por faixa de quantidade (mata 96->10 etc.)
            if quantities is not None:
                qc = quantities[global_i]
                if qo and qc and qo[1] == qc[1] and qo[0] > 0:
                    ratio = qc[0] / qo[0]
                    lo, hi = quantity_ratio_bounds
                    if ratio < lo or ratio > hi:
                        continue

            passes_raw = relevance >= min_score  # corte pré-boost (opcional)

            for boost_factor, vals in soft_values:
                v_orig = vals[orig_i]
                v_cand = vals[global_i]
                if v_orig and v_cand and v_orig == v_cand:
                    relevance *= boost_factor

            if min_score_basis == "raw_similarity":
                keep = passes_raw
            else:
                keep = relevance >= min_score
            if keep:
                candidates.append({"ean": cand_ean, "relevance": round(relevance, 6)})

        candidates.sort(key=lambda x: x["relevance"], reverse=True)
        for rank, item in enumerate(candidates[:top_k], start=1):
            item["rank"] = rank

        results.append(
            {
                "ean_origem": ean_origem,
                "sugestoes": candidates[:top_k],
            }
        )

    if normalize_relevance:
        max_relevance = max(
            (c["relevance"] for r in results for c in r["sugestoes"]),
            default=0.0,
        )
        if max_relevance > 0:
            for r in results:
                for c in r["sugestoes"]:
                    c["relevance"] = round(c["relevance"] / max_relevance, 6)

    return pd.DataFrame(results)
