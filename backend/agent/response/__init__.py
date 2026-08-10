"""Response: composes the final answer from validated evidence + policy.

``responder.py`` converts state into the final answer text (guide Section
42); ``response_models.py`` defines the structured shapes (chart/table) a
responder is allowed to return.
"""

from .responder import AI_UNAVAILABLE_MESSAGE, Responder
from .response_models import ChartData, ChartSeries, DataTable

__all__ = [
    "AI_UNAVAILABLE_MESSAGE",
    "ChartData",
    "ChartSeries",
    "DataTable",
    "Responder",
]
