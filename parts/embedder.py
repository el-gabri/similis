# -*- coding: utf-8 -*-
"""Embeddings BGE-M3 com cache incremental em Volume ou diretório local."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import List, Optional

import numpy as np
import pandas as pd

from parts.constants import EMBEDDING_MODEL_NAME, EMBEDDINGS_CACHE_VOLUME

logger = logging.getLogger(__name__)


def _text_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


class BgeM3Embedder:
    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL_NAME,
        cache_dir: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self.model_name = model_name
        self.cache_dir = cache_dir or os.environ.get(
            "SIMILIS_EMBEDDINGS_CACHE_DIR", EMBEDDINGS_CACHE_VOLUME
        )
        self._model = None
        self._device = device

    def _load_model(self):
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        logger.info("Carregando modelo %s ...", self.model_name)
        self._model = SentenceTransformer(self.model_name, device=self._device)

    def _cache_path(self, subcategoria: str) -> str:
        safe = subcategoria.replace("/", "_")
        return os.path.join(self.cache_dir, f"{safe}.parquet")

    def _read_cache(self, subcategoria: str) -> Optional[pd.DataFrame]:
        path = self._cache_path(subcategoria)
        if not os.path.isfile(path):
            return None
        try:
            return pd.read_parquet(path)
        except Exception as exc:
            logger.warning("Cache inválido em %s: %s", path, exc)
            return None

    def _write_cache(self, subcategoria: str, cache_df: pd.DataFrame):
        """Escrita ATÔMICA: tmp + os.replace.

        Um job morto no meio do write deixava um parquet corrompido — era
        descartado na releitura, mas custava um re-encode completo (10–90 min).
        """
        path = self._cache_path(subcategoria)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp_path = path + ".tmp"
        cache_df.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, path)

    def _load_cached_vectors(self, subcategoria: str, expected_dim: int) -> dict:
        """Dict ``(ean, text_hash) -> vetor`` a partir do cache válido.

        Invalidação: dimensão incompatível com o modelo carregado, ou coluna
        ``model_name`` presente e diferente (fecha o foot-gun documentado de
        trocar de modelo mantendo a mesma dimensão). Caches legados sem a
        coluna seguem aceitos quando a dimensão bate.
        """
        cache_df = self._read_cache(subcategoria)
        if (
            cache_df is None
            or not {"ean", "text_hash", "embedding"}.issubset(cache_df.columns)
            or not len(cache_df)
        ):
            return {}

        if "model_name" in cache_df.columns:
            models = set(cache_df["model_name"].dropna().unique())
            if models and models != {self.model_name}:
                logger.warning(
                    "Cache de %s descartado: model_name %s != %s.",
                    subcategoria, sorted(models), self.model_name,
                )
                return {}

        first_emb = np.asarray(cache_df.iloc[0]["embedding"], dtype=np.float32)
        if first_emb.shape[0] != expected_dim:
            logger.warning(
                "Cache de %s descartado: dim=%d incompatível com o modelo %s (dim=%d).",
                subcategoria, first_emb.shape[0], self.model_name, expected_dim,
            )
            return {}

        # zip vetorizado sobre colunas (iterrows custava minutos em
        # subcategorias grandes).
        return {
            (str(e), str(h)): np.asarray(emb, dtype=np.float32)
            for e, h, emb in zip(
                cache_df["ean"], cache_df["text_hash"], cache_df["embedding"]
            )
        }

    def encode_dataframe(
        self,
        df: pd.DataFrame,
        subcategoria: str,
        text_col: str = "text_canon",
        ean_col: str = "EAN",
        batch_size: int = 32,
    ) -> np.ndarray:
        """Matriz (n, dim) alinhada às linhas de ``df``, com cache por
        ``(ean, md5(text_canon))`` — só recomputa EANs novos ou de texto novo."""
        self._load_model()
        expected_dim = self._model.get_sentence_embedding_dimension()
        texts = df[text_col].fillna("").astype(str).tolist()
        eans = df[ean_col].astype(str).tolist()
        hashes = [_text_hash(t) for t in texts]

        cached = self._load_cached_vectors(subcategoria, expected_dim)
        n_cached_hits = 0

        embeddings_list: List[Optional[np.ndarray]] = [None] * len(texts)
        to_encode_idx: List[int] = []
        to_encode_texts: List[str] = []

        for i, (ean, th, text) in enumerate(zip(eans, hashes, texts)):
            key = (ean, th)
            if key in cached:
                embeddings_list[i] = cached[key]
                n_cached_hits += 1
            else:
                to_encode_idx.append(i)
                to_encode_texts.append(text or " ")

        if to_encode_texts:
            logger.info(
                "%s: %d embeddings do cache, %d a codificar.",
                subcategoria, n_cached_hits, len(to_encode_texts),
            )
            new_emb = self._model.encode(
                to_encode_texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            ).astype(np.float32)
            for j, idx in enumerate(to_encode_idx):
                vec = new_emb[j]
                embeddings_list[idx] = vec
                cached[(eans[idx], hashes[idx])] = vec

        # Invariante: todo índice foi preenchido (cache hit ou batch encode).
        # O código antigo tinha um fallback que re-encodava item a item aqui;
        # o caminho era inalcançável e mascararia um bug de alinhamento.
        missing = [i for i, e in enumerate(embeddings_list) if e is None]
        assert not missing, f"Embeddings ausentes para índices {missing[:5]}"

        out = np.stack(embeddings_list).astype(np.float32)

        # 100% de cache hit: o parquet em disco já contém todos os pares
        # (ean, text_hash) do universo atual — reescrevê-lo só gastaria I/O e,
        # pior, ENCOLHERIA o cache para o universo corrente (EANs que saíram
        # temporariamente do catálogo seriam descartados e recomputados ao
        # voltar). Nada novo a persistir ⇒ não escreve.
        if not to_encode_texts:
            logger.info(
                "%s: cache completo (%d hits), sem reescrita.",
                subcategoria, n_cached_hits,
            )
            return out

        cache_rows = pd.DataFrame(
            {
                "ean": eans,
                "text_hash": hashes,
                "embedding": [
                    cached[(e, h)].tolist() for e, h in zip(eans, hashes)
                ],
                "model_name": self.model_name,
            }
        )
        self._write_cache(subcategoria, cache_rows)
        return out
