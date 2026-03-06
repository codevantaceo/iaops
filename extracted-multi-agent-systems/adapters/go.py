from __future__ import annotations

from .generic import AdapterContext, GenericAdapter


class GoAdapter(GenericAdapter):
    name = "go"

    def __init__(self, ctx: AdapterContext):
        super().__init__(ctx)

    def required_files(self) -> list[str]:
        return ["go.mod"]
