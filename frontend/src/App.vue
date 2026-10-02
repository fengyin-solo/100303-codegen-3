<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">通信基站运维管理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向通信基站站点入网、动力环境监控、天馈巡检、发电保障与退网拆站的一体化基站运维管理后台。</span>
        <span class="head-user">
          <label class="identity-switch">
            施工队
            <select v-model="store.team">
              <option v-for="team in teams" :key="team" :value="team">{{ team }}</option>
            </select>
          </label>
          <label class="identity-switch">
            身份
            <select v-model="store.role">
              <option value="资料员">资料员（可核销）</option>
              <option value="施工员">施工员（仅查看）</option>
            </select>
          </label>
          <label class="identity-switch">
            姓名
            <input v-model="store.operator" class="operator-input" />
          </label>
          当前：{{ store.team }} · {{ store.operator }}（{{ store.role }}）
        </span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const teams = ['施工一队', '施工二队', '施工三队']

const navItems = [{ label: "运营概览", path: "/" }, { label: "基站台账", path: "/site" }, { label: "铁塔管理", path: "/tower" }, { label: "动力配套", path: "/power" }, { label: "蓄电池组", path: "/battery" }, { label: "发电机组", path: "/genset" }, { label: "开关电源", path: "/rectifier" }, { label: "空调管理", path: "/ac" }, { label: "天馈系统", path: "/antenna" }, { label: "传输设备", path: "/transmission" }, { label: "馈线巡检", path: "/feeder" }, { label: "防雷接地", path: "/lightningprot" }, { label: "消防设施", path: "/firealarm" }, { label: "门禁管理", path: "/dooraccess" }, { label: "巡检作业", path: "/patrol" }, { label: "油料管理", path: "/fuel" }, { label: "场租合同", path: "/rental" }, { label: "电费管理", path: "/electricbill" }, { label: "拆站管理", path: "/demolition" }, { label: "应急通信", path: "/emergency" }, { label: "节能改造", path: "/energyeff" }, { label: "光缆段台账", path: "/cable" }]
</script>

<style scoped>
.identity-switch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}
.identity-switch select,
.operator-input {
  font-size: 12px;
  padding: 2px 4px;
}
.operator-input {
  width: 80px;
}
</style>
