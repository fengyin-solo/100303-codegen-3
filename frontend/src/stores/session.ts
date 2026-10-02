import { defineStore } from 'pinia'

interface TeamProfile {
  teamId: string
  teamName: string
  role: string
}

const TEAMS: TeamProfile[] = [
  { teamId: 'T01', teamName: '闽工一队', role: '资料员' },
  { teamId: 'T01', teamName: '闽工一队', role: '现场班长' },
  { teamId: 'T02', teamName: '粤工二队', role: '资料员' },
  { teamId: 'T02', teamName: '粤工二队', role: '现场班长' },
]

const STORAGE_KEY = 'cable-session-profile'

function loadProfile(): TeamProfile {
  const fallback = TEAMS[0]
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<TeamProfile>
    return TEAMS.find((item) => item.teamId === parsed.teamId && item.role === parsed.role) ?? fallback
  } catch {
    return fallback
  }
}

export const useSessionStore = defineStore('session', {
  state: () => {
    const profile = loadProfile()
    return {
      operator: '值班管理员',
      shiftLabel: '白班 08:00-20:00',
      scope: '通信基站运维管理平台',
      teamId: profile.teamId,
      teamName: profile.teamName,
      role: profile.role,
      teams: TEAMS,
    }
  },
  getters: {
    canOperate: (state) => state.operator.length > 0,
    /** 只有本施工队资料员能核销占用：其他角色、其他队伍一律只读。 */
    canWriteCable(state): boolean {
      return state.role === '资料员'
    },
    identityLabel(state): string {
      return `${state.teamName} · ${state.role}`
    },
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    switchProfile(teamId: string, role: string) {
      const match = this.teams.find((item) => item.teamId === teamId && item.role === role)
      if (!match) return
      this.teamId = match.teamId
      this.teamName = match.teamName
      this.role = match.role
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(match))
    },
  },
})
