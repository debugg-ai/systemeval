"""Pipeline adapter for Django pipeline evaluation.

Note: This adapter is 1440 lines and should be decomposed into:
- adapter.py (main adapter logic)
- webhook_client.py (webhook handling)
- metric_collectors.py (metric collection)
- evaluator.py (evaluation logic)
- result_builder.py (result building)

For now, it's kept as a single file for backward compatibility.
"""

from .adapter import PipelineAdapter

__all__ = ["PipelineAdapter"]
