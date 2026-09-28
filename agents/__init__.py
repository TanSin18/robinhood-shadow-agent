"""Application agents plus a namespace bridge to the OpenAI Agents SDK.

The official SDK installs under the top-level name :mod:`agents`, which is also
the repository layout required by the v4 specification. Extending this
package's search path lets local modules and the installed SDK's submodules
coexist without copying SDK code.
"""

from importlib import metadata
from pathlib import Path

try:
    _sdk_path = Path(metadata.distribution("openai-agents").locate_file("agents"))
except metadata.PackageNotFoundError:
    _sdk_path = None

if _sdk_path is not None and _sdk_path.is_dir() and str(_sdk_path) not in __path__:
    __path__.append(str(_sdk_path))
