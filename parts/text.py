# -*- coding: utf-8 -*-
"""Limpeza de texto compartilhada (normalizer + sintéticos)."""
from __future__ import annotations

import re
from typing import Any, List

import pandas as pd

from parts.units import ascii_fold


def clean_text(text: Any) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    text = str(text).upper()
    text = ascii_fold(text)
    text = re.sub(r"[^A-Z0-9_ ]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize_for_removal(value: str) -> List[str]:
    cleaned = clean_text(value)
    if not cleaned:
        return []
    return [t for t in cleaned.split() if len(t) > 1]
