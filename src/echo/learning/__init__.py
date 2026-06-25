"""Deep Real-Time Learning module — personalization + predictive analytics + meta-learning.

See PROJECT ECHO section 16 (DEEP REAL-TIME LEARNING).

Exports:
    LearningEngine  - top-level coordinator used by CognitivePipeline
    MetaLearningEngine - tracks how ECHO learns best (module 1)
"""

from echo.learning.engine import LearningEngine
from echo.learning.meta_learning import MetaLearningEngine

__all__ = ["LearningEngine", "MetaLearningEngine"]
