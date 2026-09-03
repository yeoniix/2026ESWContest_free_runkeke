"""역할 기반 접근 제어 (HS-SIID-002 p6 표6, HMI-001).

권한 분리 구조를 세우기 위해 역할을 헤더로 받는다. 인증이 아니므로 실사용
전에는 서명된 토큰으로 교체해야 한다. /api/v2/config PUT만은 "서명된 설정"이
요구사항이라 routes_api_v2.py에서 HMAC 서명을 검증한다.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

Role = str
ROLES = ("observer", "commander", "tester", "maintainer")


def get_role(x_hs_role: str | None = Header(default="observer")) -> Role:
    if x_hs_role not in ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown role '{x_hs_role}'")
    return x_hs_role


def get_actor_id(x_hs_actor: str | None = Header(default="unknown")) -> str:
    return x_hs_actor or "unknown"


def require_roles(*allowed: Role):
    def _dependency(role: Role = Header(default="observer", alias="X-HS-Role")) -> Role:
        if role not in ROLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown role '{role}'")
        if role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role '{role}' cannot perform this action (requires one of {allowed})",
            )
        return role

    return _dependency
