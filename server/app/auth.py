"""역할 기반 접근 제어 (placeholder).

출처: HS-SIID-002 p6 표6 "로컬 API v2" 권한 컬럼(observer/commander/tester/
maintainer). 대회 MVP 단계에서는 실제 로그인·서명 체계 대신 헤더로 역할을
받는다 — 이는 진짜 인증이 아니라 "권한이 분리되어 있어야 한다"는 HMI-001
구조를 먼저 세워두는 것이다. 실사용 전에는 반드시 서명된 토큰으로 교체해야
한다 (CLAUDE 주의: 이 auth.py는 프로덕션 인증이 아님).

/api/v2/config PUT만은 "서명된 설정"이 명문 요구사항이라 HMAC 서명 검증을
최소 구현해 둔다(server/app/routes_api_v2.py 참고).
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
