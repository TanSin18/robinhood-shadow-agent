from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VersionedPrompt:
    name: str
    version: str
    text: str


class PromptRegistry:
    _SAFE = re.compile(r"^[a-z][a-z0-9_]*$")

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def load(self, name: str, version: str) -> VersionedPrompt:
        if not self._SAFE.fullmatch(name) or not self._SAFE.fullmatch(version):
            raise ValueError("invalid prompt name or version")
        path = self.root / f"{name}_{version}.md"
        text = path.read_text(encoding="utf-8").strip()
        return VersionedPrompt(name=name, version=f"{name}_{version}", text=text)

