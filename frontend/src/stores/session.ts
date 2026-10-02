import { defineStore } from 'pinia'

/** 操作人身份：施工队决定能看哪队的缆，角色里只有「资料员」能核销占用。 */
export type Role = '资料员' | '施工员'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '李资料',
    team: '施工一队',
    role: '资料员' as Role,
    shiftLabel: '白班 08:00-20:00',
    scope: '通信基站运维管理平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    isClerk(): boolean {
      return this.role === '资料员'
    },
    /** 中文身份信息百分号编码后放进请求头（HTTP 头只允许 ASCII）。 */
    authHeaders(): Record<string, string> {
      return {
        'X-Team': encodeURIComponent(this.team),
        'X-Role': encodeURIComponent(this.role),
        'X-Operator': encodeURIComponent(this.operator),
      }
    },
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setIdentity(team: string, role: Role, operator: string) {
      this.team = team
      this.role = role
      this.operator = operator
    },
  },
})
