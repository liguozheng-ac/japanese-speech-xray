"""Descriptive pronunciation hypothesis evidence; no learner decision semantics."""

from .models import Target, Hypotheses, RealizationEvidence
from .variants import derive_hypotheses
from .lexicon import CONDITIONS, override_lexicon
from .geometry import observe, selection, paired_displacements
from .scores import compare_scores

__all__ = ["Target", "Hypotheses", "RealizationEvidence", "derive_hypotheses",
           "CONDITIONS", "override_lexicon", "observe", "selection",
           "paired_displacements", "compare_scores"]
