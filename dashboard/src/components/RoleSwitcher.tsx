// 대회 MVP 단계의 자리표시 역할 선택기. 실제 로그인 없이 X-HS-Role 헤더값을
// 바꿔가며 observer/commander/tester/maintainer 권한 분리를 시연하기 위한
// 것으로, 실사용 전에는 반드시 서명된 인증으로 교체해야 한다.
import type { Role } from "../types/device";

interface RoleSwitcherProps {
  role: Role;
  actorId: string;
  onRoleChange: (role: Role) => void;
  onActorChange: (actorId: string) => void;
}

const ROLES: { value: Role; label: string }[] = [
  { value: "observer", label: "관측자" },
  { value: "commander", label: "지휘관" },
  { value: "tester", label: "시험 담당" },
  { value: "maintainer", label: "정비 담당" },
];

export default function RoleSwitcher({ role, actorId, onRoleChange, onActorChange }: RoleSwitcherProps) {
  return (
    <div className="role-switcher">
      <label>
        역할
        <select value={role} onChange={(e) => onRoleChange(e.target.value as Role)}>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        사용자 ID
        <input value={actorId} onChange={(e) => onActorChange(e.target.value)} placeholder="예: CDR1" />
      </label>
    </div>
  );
}
