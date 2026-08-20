"""Spectral Loom: compile music into a source-grounded semantic timeline.

This package currently contains the compiler's *boundary* and nothing else: the
versioned data contracts (:mod:`spectral_loom.contracts`), their generated JSON
Schemas (:mod:`spectral_loom.schemas`), and an infrastructure-only CLI
(:mod:`spectral_loom.cli`).

There is no generator, no separator, no analyser, and no renderer. Nothing here
downloads a model or touches audio.
"""

__version__ = "0.0.1"

__all__ = ["__version__"]
