from __future__ import annotations

import os

from oedk.models import DownloadPlan, DownloadRequest
from .base import Adapter


class ManualAuthAdapter(Adapter):
    def validate_config(self, request: DownloadRequest) -> list[str]:
        missing = [name for name in request.source.required_credentials if not os.getenv(name)]
        return [f"missing environment variable: {name}" for name in missing]

    def plan(self, request: DownloadRequest) -> DownloadPlan:
        errors = self.validate_config(request)
        message = "manual or authenticated source"
        if errors:
            message += "; " + "; ".join(errors)
        return DownloadPlan(request=request, files=[], message=message)
