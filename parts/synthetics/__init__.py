# -*- coding: utf-8 -*-
"""Registro de atributos sintéticos.

Importar este pacote popula ``REGISTRY`` (cada módulo registra seus extratores
via decorator). Para adicionar um sintético novo: criar/editar UM módulo aqui,
registrar com ``@register("nome", required_metadata_keys={...})`` — data_loader
e normalizer derivam tudo do registro.
"""
from parts.synthetics.base import REGISTRY, SyntheticSpec, register, resolve_column

# A ordem de import define a ordem de cômputo (mantém a ordem histórica do
# normalizer antigo: quantity/size/metragem/audience, depois os demais).
from parts.synthetics import quantity  # noqa: F401,E402
from parts.synthetics import fraldas  # noqa: F401,E402
from parts.synthetics import leite  # noqa: F401,E402
from parts.synthetics import formula  # noqa: F401,E402
from parts.synthetics import sabonete  # noqa: F401,E402
from parts.synthetics import papel  # noqa: F401,E402
from parts.synthetics import misc  # noqa: F401,E402
from parts.synthetics import desodorante  # noqa: F401,E402
from parts.synthetics import higiene_oral  # noqa: F401,E402
from parts.synthetics import bebidas  # noqa: F401,E402
from parts.synthetics import bebe  # noqa: F401,E402

SYNTHETIC_ATTRIBUTES = frozenset(REGISTRY.keys())

__all__ = [
    "REGISTRY",
    "SYNTHETIC_ATTRIBUTES",
    "SyntheticSpec",
    "register",
    "resolve_column",
]
