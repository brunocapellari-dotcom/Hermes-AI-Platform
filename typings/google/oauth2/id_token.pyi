from collections.abc import Mapping
from typing import Any

def verify_oauth2_token(
    id_token: str,
    request: Any,
    audience: str | None = ...,
) -> Mapping[str, Any]: ...

def fetch_id_token(
    request: Any,
    audience: str,
) -> str: ...
