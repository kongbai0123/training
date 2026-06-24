from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict
import os
import secrets
from pathlib import Path


@dataclass(frozen=True)
class BootstrapPayload:
    token: str
    started_at: str
    expires_at: str
    version: str
    environment: str


class LocalSession:
    def __init__(self) -> None:
        self._token = secrets.token_urlsafe(32)
        self._started_at = datetime.now(timezone.utc)
        self._ttl_minutes = int(os.environ.get("VTS_SESSION_TTL_MIN", "720"))

    @property
    def token(self) -> str:
        return self._token

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > (self._started_at + timedelta(minutes=self._ttl_minutes))

    def payload(self, version: str, environment: str) -> BootstrapPayload:
        return BootstrapPayload(
            token=self._token,
            started_at=self._started_at.isoformat(),
            expires_at=(self._started_at + timedelta(minutes=self._ttl_minutes)).isoformat(),
            version=version,
            environment=environment,
        )

    def rotate(self) -> str:
        self.__init__()
        return self._token

    def validate(self, token: str) -> bool:
        if not token:
            return False
        if self.is_expired:
            return False
        return secrets.compare_digest(self._token, token)


_local_session = LocalSession()


def get_session() -> LocalSession:
    return _local_session


def current_bootstrap(version: str, environment: str) -> Dict[str, str]:
    data = _local_session.payload(version, environment)
    return data.__dict__

def validate_token(token: str) -> bool:
    return _local_session.validate(token)
