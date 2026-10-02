<template>
  <section class="page" data-module="cable">
    <header class="page-head">
      <div>
        <h2>光缆段占用台账</h2>
        <p class="page-desc">
          光缆段按起点、终点与占用的管道孔位登记核销；同一管道孔位一孔一缆，冲突拦下；
          杆路按杆位加挂。状态沿 待勘测 → 已勘测 → 已分配 → 已敷设 → 已核实 推进。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记光缆段</button>
        <button class="btn" type="button" @click="openLegacy">存量光缆补录</button>
        <button class="btn" type="button" @click="exportRows">导出台账</button>
      </div>
    </header>

    <p v-if="!store.isClerk" class="perm-hint">
      当前身份为「{{ store.role }}」：只能查看与推进本队勘测/核实，敷设核销与释放占用须切换为资料员。
    </p>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="tab"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- 光缆段 -->
    <div v-if="activeTab === 'cables'">
      <form class="filter-bar" @submit.prevent="reloadCables">
        <label class="filter-item">
          <span>光缆编号/起终点</span>
          <input v-model="cableFilters.keyword" placeholder="按编号、起点、终点检索" />
        </label>
        <label class="filter-item">
          <span>状态</span>
          <select v-model="cableFilters.status">
            <option value="">全部</option>
            <option v-for="s in statusOrder" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetCableFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>光缆编号</th><th>起点</th><th>终点</th><th>芯数</th><th>施工队</th>
            <th>状态</th><th>敷设进度</th><th>当前断点</th><th>登记日期</th><th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in cables" :key="String(row.id)">
            <td><button class="link" type="button" @click="openDetail(row)">{{ row['光缆编号'] }}</button></td>
            <td>{{ row['起点'] }}</td>
            <td>{{ row['终点'] }}</td>
            <td>{{ row['芯数'] }}</td>
            <td>{{ row['施工队'] }}</td>
            <td><span class="status-badge" :class="statusClass(row.status)">{{ row.status }}</span></td>
            <td>{{ row['已敷设孔位'] }} / {{ row['孔位总数'] }}</td>
            <td>{{ row['当前断点'] || '—' }}</td>
            <td>{{ row['登记日期'] }}</td>
            <td class="row-actions">
              <button
                v-for="act in actionsFor(row)"
                :key="act.key"
                class="link"
                type="button"
                :title="act.hint"
                @click="onCableAction(act.key, row)"
              >
                {{ act.label }}
              </button>
            </td>
          </tr>
          <tr v-if="!cables.length">
            <td colspan="10" class="empty-state">暂无光缆段，可先登记或补录存量</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot"><span>共 {{ cableTotal }} 段光缆</span></footer>
    </div>

    <!-- 管道孔位 -->
    <div v-if="activeTab === 'ducts'">
      <form class="filter-bar" @submit.prevent="reloadResources">
        <label class="filter-item">
          <span>管道编号</span>
          <input v-model="resourceKeyword" placeholder="按管道编号检索" />
        </label>
        <button class="btn" type="submit">查询</button>
      </form>
      <table v-for="d in ducts" :key="String(d.id)" class="data-table resource-table">
        <caption>{{ d['管道编号'] }}（{{ d['起点井'] }} → {{ d['终点井'] }}）：共 {{ d['孔位列表'].length }} 孔，占用 {{ d['占用孔数'] }}，剩余 {{ d['剩余孔数'] }} 孔</caption>
        <thead><tr><th>孔位</th><th>状态</th><th>占用光缆</th><th>占用性质</th></tr></thead>
        <tbody>
          <tr v-for="h in d['孔位状态']" :key="h.孔位">
            <td>{{ h.孔位 }}</td>
            <td>
              <span :class="h.占用中 ? 'hole-used' : 'hole-free'">
                {{ h.占用中 ? '占用中' : '空闲' }}
              </span>
            </td>
            <td>{{ h.占用光缆 || '—' }}</td>
            <td>{{ h.占用中 ? (h.历史 ? '历史占用' : '新建占用') : '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!ducts.length" class="empty-state">没有匹配的管道</p>
    </div>

    <!-- 杆路加挂 -->
    <div v-if="activeTab === 'poles'">
      <form class="filter-bar" @submit.prevent="reloadResources">
        <label class="filter-item">
          <span>杆路编号</span>
          <input v-model="resourceKeyword" placeholder="按杆路编号检索" />
        </label>
        <button class="btn" type="submit">查询</button>
      </form>
      <table v-for="p in poles" :key="String(p.id)" class="data-table resource-table">
        <caption>{{ p['杆路编号'] }}（{{ p['起点杆'] }} → {{ p['终点杆'] }}）：共 {{ p['杆位列表'].length }} 根杆，同一杆支持多缆加挂</caption>
        <thead><tr><th>杆位</th><th>已加挂缆数</th><th>加挂光缆</th><th>占用性质</th></tr></thead>
        <tbody>
          <tr v-for="h in p['孔位状态']" :key="h.孔位">
            <td>{{ h.孔位 }}</td>
            <td>{{ poleCount(p, h.孔位) }}</td>
            <td>{{ h.占用光缆 || '—' }}{{ poleCount(p, h.孔位) > 1 ? ` 等 ${poleCount(p, h.孔位)} 条` : '' }}</td>
            <td>{{ h.占用中 ? (h.历史 ? '含历史占用' : '新建占用') : '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!poles.length" class="empty-state">没有匹配的杆路</p>
    </div>

    <!-- 占用核销台账 -->
    <div v-if="activeTab === 'ledger'">
      <form class="filter-bar" @submit.prevent="reloadLedger">
        <label class="filter-item">
          <span>资源类型</span>
          <select v-model="ledgerFilters.kind">
            <option value="">全部</option>
            <option value="管道">管道</option>
            <option value="杆路">杆路</option>
          </select>
        </label>
        <label class="filter-item">
          <span>资源编码</span>
          <input v-model="ledgerFilters.code" placeholder="如 GD-001" />
        </label>
        <label class="filter-item">
          <span>光缆编号</span>
          <input v-model="ledgerFilters.cable" placeholder="如 FO-A01" />
        </label>
        <label class="filter-item">
          <span>占用性质</span>
          <select v-model="ledgerFilters.historical">
            <option value="">全部</option>
            <option value="false">新建占用</option>
            <option value="true">历史占用</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
      </form>
      <table class="data-table">
        <thead>
          <tr>
            <th>光缆编号</th><th>施工队</th><th>敷设序号</th><th>资源</th><th>孔位/杆位</th>
            <th>敷设状态</th><th>占用状态</th><th>性质</th><th>核销记录</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in ledger" :key="String(o.id)">
            <td>{{ o['光缆编号'] }}</td>
            <td>{{ o['施工队'] }}</td>
            <td>{{ o['序号'] }}</td>
            <td>{{ o['资源类型'] }} {{ o['资源编码'] }}</td>
            <td>{{ o['孔位'] }}</td>
            <td>{{ o['敷设状态'] }}</td>
            <td>{{ o['占用状态'] }}</td>
            <td>{{ o['历史'] ? '历史占用' : '新建占用' }}</td>
            <td class="audit-cell">
              <template v-if="o['释放时间']">释放：{{ o['释放人'] }} {{ o['释放时间'] }}（{{ o['释放原因'] }}）</template>
              <template v-else-if="o['敷设核销时间']">敷设：{{ o['敷设核销人'] }} {{ o['敷设核销时间'] }}</template>
              <template v-else-if="o['分配人']">分配：{{ o['分配人'] }}</template>
              <template v-else>历史补录</template>
            </td>
            <td>
              <button
                v-if="canRelease(o)"
                class="link danger"
                type="button"
                @click="openRelease(o)"
              >
                核销占用
              </button>
              <span v-else class="muted-text">{{ releaseHint(o) }}</span>
            </td>
          </tr>
          <tr v-if="!ledger.length">
            <td colspan="10" class="empty-state">没有匹配的占用记录</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot"><span>共 {{ ledgerTotal }} 条占用记录</span></footer>
    </div>

    <!-- 登记光缆段 -->
    <div v-if="createModal.open" class="modal-mask" @click.self="createModal.open = false">
      <div class="modal">
        <h3>登记光缆段</h3>
        <p class="modal-tip">同一起点、终点（互换也算同一段）只记一次；登记后从「待勘测」起步，不能直接登记敷设。</p>
        <div class="form-grid">
          <label><span>光缆编号 *</span><input v-model="createModal.form['光缆编号']" placeholder="如 FO-A05" /></label>
          <label><span>起点 *</span><input v-model="createModal.form['起点']" /></label>
          <label><span>终点 *</span><input v-model="createModal.form['终点']" /></label>
          <label><span>芯数 *</span><input v-model="createModal.form['芯数']" placeholder="如 48芯" /></label>
          <label><span>施工队</span><input v-model="createModal.form['施工队']" :placeholder="store.team" /></label>
          <label><span>备注</span><input v-model="createModal.form['备注']" /></label>
        </div>
        <div class="modal-actions">
          <button class="btn" type="button" @click="createModal.open = false">取消</button>
          <button class="btn primary" type="button" @click="submitCreate">提交登记</button>
        </div>
      </div>
    </div>

    <!-- 存量补录 -->
    <div v-if="legacyModal.open" class="modal-mask wide" @click.self="legacyModal.open = false">
      <div class="modal">
        <h3>存量光缆补录</h3>
        <p class="modal-tip">按敷设顺序补占用的杆路与管道孔位，光缆直接落成「已核实」，占用标记为历史占用并永久保留。管道孔位冲突的会跳过并说明。</p>
        <div class="form-grid">
          <label><span>光缆编号 *</span><input v-model="legacyModal.form['光缆编号']" /></label>
          <label><span>起点 *</span><input v-model="legacyModal.form['起点']" /></label>
          <label><span>终点 *</span><input v-model="legacyModal.form['终点']" /></label>
          <label><span>芯数 *</span><input v-model="legacyModal.form['芯数']" /></label>
          <label><span>敷设日期</span><input v-model="legacyModal.form['敷设日期']" placeholder="如 2024-05-01" /></label>
        </div>
        <SlotEditor :slots="legacyModal.slots" :ducts="ducts" :poles="poles" @add="addSlot(legacyModal.slots)" @remove="removeSlot(legacyModal.slots, $event)" />
        <div class="modal-actions">
          <button class="btn" type="button" @click="legacyModal.open = false">取消</button>
          <button class="btn primary" type="button" @click="submitLegacy">补录并落成已核实</button>
        </div>
      </div>
    </div>

    <!-- 分配孔位 -->
    <div v-if="slotModal.open" class="modal-mask wide" @click.self="slotModal.open = false">
      <div class="modal">
        <h3>为 {{ slotModal.cable?.['光缆编号'] }} 分配孔位/杆位</h3>
        <p class="modal-tip">管道同一孔位被占用时本批分配会整批拦下，并告知与哪条光缆冲突；杆路同一杆位可多缆加挂。</p>
        <SlotEditor :slots="slotModal.slots" :ducts="ducts" :poles="poles" @add="addSlot(slotModal.slots)" @remove="removeSlot(slotModal.slots, $event)" />
        <div class="modal-actions">
          <button class="btn" type="button" @click="slotModal.open = false">取消</button>
          <button class="btn primary" type="button" @click="submitAllocate">提交分配</button>
        </div>
      </div>
    </div>

    <!-- 明细 -->
    <div v-if="detailModal.open && detailModal.cable" class="modal-mask wide" @click.self="detailModal.open = false">
      <div class="modal">
        <h3>{{ detailModal.cable['光缆编号'] }} 占用明细</h3>
        <p class="modal-tip">
          {{ detailModal.cable['起点'] }} → {{ detailModal.cable['终点'] }} ·
          {{ detailModal.cable['施工队'] }} · 状态 {{ detailModal.cable.status }} ·
          已敷设 {{ detailModal.cable['已敷设孔位'] }}/{{ detailModal.cable['孔位总数'] }}
          <template v-if="detailModal.cable['当前断点']"> · 断点：{{ detailModal.cable['当前断点'] }}</template>
        </p>
        <table class="data-table">
          <thead>
            <tr><th>序号</th><th>资源</th><th>孔位/杆位</th><th>敷设状态</th><th>占用状态</th><th>性质</th><th>核销记录</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="o in detailModal.cable['占用明细']" :key="String(o.id)">
              <td>{{ o['序号'] }}</td>
              <td>{{ o['资源类型'] }} {{ o['资源编码'] }}</td>
              <td>{{ o['孔位'] }}</td>
              <td>{{ o['敷设状态'] }}</td>
              <td>{{ o['占用状态'] }}</td>
              <td>{{ o['历史'] ? '历史占用' : '新建占用' }}</td>
              <td class="audit-cell">
                <template v-if="o['释放时间']">释放：{{ o['释放人'] }} {{ o['释放时间'] }}</template>
                <template v-else-if="o['敷设核销时间']">敷设：{{ o['敷设核销人'] }} {{ o['敷设核销时间'] }}</template>
                <template v-else-if="o['分配人']">分配：{{ o['分配人'] }}</template>
                <template v-else>历史补录</template>
              </td>
              <td>
                <button
                  v-if="o['敷设状态'] === '已分配' && o['占用状态'] === '占用中' && sameTeam(detailModal.cable) && store.isClerk && detailModal.cable.status !== '已核实'"
                  class="link"
                  type="button"
                  @click="writeOffAt(detailModal.cable, o['序号'])"
                >
                  敷设核销
                </button>
                <button
                  v-if="canRelease(o)"
                  class="link danger"
                  type="button"
                  @click="openRelease(o)"
                >
                  核销占用
                </button>
                <span v-if="o['历史']" class="muted-text">历史保留</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn" type="button" @click="detailModal.open = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 核销占用 -->
    <div v-if="releaseModal.open" class="modal-mask" @click.self="releaseModal.open = false">
      <div class="modal">
        <h3>核销占用（{{ store.team }} 资料员）</h3>
        <p class="modal-tip">
          核销后 {{ releaseModal.occ?.['光缆编号'] }} 对 {{ releaseModal.occ?.['资源编码'] }}
          {{ releaseModal.occ?.['孔位'] }} 的占用释放，孔位可重新分配；历史占用不允许核销。
        </p>
        <label class="block-label">
          <span>核销原因 *</span>
          <textarea v-model="releaseModal.reason" rows="3" placeholder="如：现场改路、光缆拆除"></textarea>
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="releaseModal.open = false">取消</button>
          <button class="btn primary danger-btn" type="button" @click="submitRelease">确认核销</button>
        </div>
      </div>
    </div>

    <footer class="page-foot">
      <span v-if="toast.show" :class="toast.ok ? 'ok-text' : 'error-text'">{{ toast.message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { defineComponent, h, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, any>
type SlotDraft = { 资源类型: '管道' | '杆路'; 资源编码: string; 孔位: string }

const store = useSessionStore()

const tabs = [
  { key: 'cables', label: '光缆段' },
  { key: 'ducts', label: '管道孔位' },
  { key: 'poles', label: '杆路加挂' },
  { key: 'ledger', label: '占用核销台账' },
] as const
const activeTab = ref<(typeof tabs)[number]['key']>('cables')
const statusOrder = ['待勘测', '已勘测', '已分配', '已敷设', '已核实']

const toast = reactive({ show: false, ok: true, message: '' })
let toastTimer: ReturnType<typeof setTimeout> | undefined
function notify(ok: boolean, message: string) {
  toast.show = true
  toast.ok = ok
  toast.message = message
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.show = false), 8000)
}

async function apiPost(path: string, values: Record<string, any>): Promise<Row> {
  const response = await request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...store.authHeaders },
    body: JSON.stringify({ values }),
  })
  return (await response.json()) as Row
}

// ---------- 看板 ----------
const stats = ref<Record<string, number>>({})
const statCards = ref<{ label: string; value: number }[]>([])
async function reloadStats() {
  const response = await request('/api/cable/stats')
  stats.value = await response.json()
  statCards.value = [
    { label: '光缆段总数', value: stats.value['光缆段总数'] ?? 0 },
    { label: '待勘测', value: stats.value['待勘测'] ?? 0 },
    { label: '敷设中断（已敷设未核实）', value: stats.value['敷设中断'] ?? 0 },
    { label: '已核实', value: stats.value['已核实'] ?? 0 },
    { label: '占用中记录', value: stats.value['占用记录'] ?? 0 },
    { label: '管道剩余孔位', value: stats.value['管道剩余孔位'] ?? 0 },
    { label: '历史占用（保留）', value: stats.value['历史占用'] ?? 0 },
  ]
}

// ---------- 光缆段 ----------
const cables = ref<Row[]>([])
const cableTotal = ref(0)
const cableFilters = reactive({ keyword: '', status: '' })

async function reloadCables() {
  const params = new URLSearchParams()
  if (cableFilters.keyword) params.set('keyword', cableFilters.keyword)
  if (cableFilters.status) params.set('status', cableFilters.status)
  const response = await request(`/api/cable?${params.toString()}`)
  const payload = await response.json()
  cables.value = payload.items ?? []
  cableTotal.value = payload.total ?? 0
}
function resetCableFilters() {
  cableFilters.keyword = ''
  cableFilters.status = ''
  void reloadCables()
}

function sameTeam(row: Row) {
  return row?.['施工队'] === store.team
}
function actionsFor(row: Row): { key: string; label: string; hint: string }[] {
  const mine = sameTeam(row)
  const acts: { key: string; label: string; hint: string }[] = []
  if (row.status === '待勘测' && mine) acts.push({ key: 'survey', label: '完成勘测', hint: '' })
  if (['已勘测', '已分配'].includes(row.status) && mine)
    acts.push({ key: 'allocate', label: '分配孔位', hint: '' })
  if (['已分配', '已敷设'].includes(row.status) && mine)
    acts.push({
      key: 'writeoff',
      label: '敷设核销（断点续销）',
      hint: store.isClerk ? '' : '仅本队资料员可核销',
    })
  if (row.status === '已敷设' && mine) acts.push({ key: 'verify', label: '提交核实', hint: '' })
  if (!mine) acts.push({ key: 'readonly', label: '他队：仅查看', hint: '跨队只能查看' })
  return acts
}
async function onCableAction(key: string, row: Row) {
  if (key === 'readonly') {
    notify(false, `光缆 ${row['光缆编号']} 属于 ${row['施工队']}，${store.team} 打开只能查看`)
    return
  }
  if (key === 'allocate') {
    openAllocate(row)
    return
  }
  if (key === 'writeoff' && !store.isClerk) {
    notify(false, '只有本施工队的资料员能核销敷设，请在右上角切换为资料员身份')
    return
  }
  const actionMap: Record<string, string> = {
    survey: '完成勘测',
    writeoff: '敷设核销',
    verify: '提交核实',
  }
  try {
    const result = await apiPost(`/api/cable/${row.id}/actions`, { action: actionMap[key] })
    notify(Boolean(result.ok), String(result.message))
    if (result.ok) {
      await reloadCables()
      await reloadStats()
      if (detailModal.open) await refreshDetail()
    }
  } catch (error) {
    notify(false, error instanceof Error ? error.message : '操作失败')
  }
}
function statusClass(status: string) {
  return {
    待勘测: 'st-survey',
    已勘测: 'st-surveyed',
    已分配: 'st-allocated',
    已敷设: 'st-laid',
    已核实: 'st-verified',
  }[status] ?? ''
}

// ---------- 资源（管道/杆路） ----------
const ducts = ref<Row[]>([])
const poles = ref<Row[]>([])
const resourceKeyword = ref('')
async function reloadResources() {
  const buildUrl = (kind: string) => {
    const params = new URLSearchParams({ kind })
    if (resourceKeyword.value.trim()) params.set('keyword', resourceKeyword.value.trim())
    return `/api/cable/resources?${params.toString()}`
  }
  const [d, p] = await Promise.all([
    request(buildUrl('管道')).then((r) => r.json()),
    request(buildUrl('杆路')).then((r) => r.json()),
  ])
  ducts.value = d.items ?? []
  poles.value = p.items ?? []
}
function poleCount(pole: Row, pos: string): number {
  return Number(pole['各杆加挂缆数']?.[pos] ?? 0)
}

// ---------- 核销台账 ----------
const ledger = ref<Row[]>([])
const ledgerTotal = ref(0)
const ledgerFilters = reactive({ kind: '', code: '', cable: '', historical: '' })
async function reloadLedger() {
  const params = new URLSearchParams()
  if (ledgerFilters.kind) params.set('kind', ledgerFilters.kind)
  if (ledgerFilters.code) params.set('code', ledgerFilters.code)
  if (ledgerFilters.cable) params.set('cable', ledgerFilters.cable)
  if (ledgerFilters.historical) params.set('historical', ledgerFilters.historical)
  params.set('size', '200')
  const response = await request(`/api/cable/occupancies?${params.toString()}`)
  const payload = await response.json()
  ledger.value = payload.items ?? []
  ledgerTotal.value = payload.total ?? 0
}
function canRelease(o: Row) {
  return o['占用状态'] === '占用中' && !o['历史'] && o['施工队'] === store.team && store.isClerk
}
function releaseHint(o: Row): string {
  if (o['占用状态'] !== '占用中') return '已核销'
  if (o['历史']) return '历史占用保留'
  if (o['施工队'] !== store.team) return `${o['施工队']}占用，本队仅查看`
  if (!store.isClerk) return '仅资料员可核销'
  return ''
}

async function switchTab(key: (typeof tabs)[number]['key']) {
  activeTab.value = key
  if (key === 'ducts' || key === 'poles') await reloadResources()
  if (key === 'ledger') await reloadLedger()
}

// ---------- 登记 ----------
const createModal = reactive({
  open: false,
  form: { 光缆编号: '', 起点: '', 终点: '', 芯数: '', 施工队: '', 备注: '' },
})
function openCreate() {
  createModal.form = { 光缆编号: '', 起点: '', 终点: '', 芯数: '', 施工队: '', 备注: '' }
  createModal.open = true
}
async function submitCreate() {
  try {
    const result = await apiPost('/api/cable', { ...createModal.form })
    notify(Boolean(result.ok), String(result.message))
    if (result.ok) {
      createModal.open = false
      activeTab.value = 'cables'
      await reloadCables()
      await reloadStats()
    }
  } catch (error) {
    notify(false, error instanceof Error ? error.message : '登记失败')
  }
}

// ---------- 分配 ----------
const slotModal = reactive<{ open: boolean; cable: Row | null; slots: SlotDraft[] }>({
  open: false,
  cable: null,
  slots: [],
})
function openAllocate(cable: Row) {
  slotModal.cable = cable
  slotModal.slots = [{ 资源类型: '管道', 资源编码: '', 孔位: '' }]
  slotModal.open = true
}
async function submitAllocate() {
  const slots = normalizeSlots(slotModal.slots)
  if (!slots.length) {
    notify(false, '请至少填写一行完整的孔位/杆位')
    return
  }
  try {
    const result = await apiPost(`/api/cable/${slotModal.cable?.id}/actions`, {
      action: '分配孔位',
      slots,
    })
    notify(Boolean(result.ok), String(result.message))
    if (result.ok) {
      slotModal.open = false
      await reloadCables()
      await reloadResources()
      await reloadStats()
    }
  } catch (error) {
    notify(false, error instanceof Error ? error.message : '分配失败')
  }
}

// ---------- 存量补录 ----------
const legacyModal = reactive({
  open: false,
  form: { 光缆编号: '', 起点: '', 终点: '', 芯数: '', 敷设日期: '' },
  slots: [] as SlotDraft[],
})
function openLegacy() {
  legacyModal.form = { 光缆编号: '', 起点: '', 终点: '', 芯数: '', 敷设日期: '' }
  legacyModal.slots = [{ 资源类型: '管道', 资源编码: '', 孔位: '' }]
  legacyModal.open = true
}
async function submitLegacy() {
  const slots = normalizeSlots(legacyModal.slots)
  if (!slots.length) {
    notify(false, '请按敷设顺序至少填写一行完整的孔位/杆位')
    return
  }
  try {
    const result = await apiPost('/api/cable/legacy/backfill', { ...legacyModal.form, slots })
    notify(Boolean(result.ok), String(result.message))
    if (result.ok) {
      legacyModal.open = false
      activeTab.value = 'cables'
      await Promise.all([reloadCables(), reloadResources(), reloadLedger(), reloadStats()])
    }
  } catch (error) {
    notify(false, error instanceof Error ? error.message : '补录失败')
  }
}

// ---------- 明细 / 核销 ----------
const detailModal = reactive<{ open: boolean; cable: Row | null }>({ open: false, cable: null })
async function openDetail(row: Row) {
  detailModal.open = true
  detailModal.cable = null
  await refreshDetail(row.id)
}
async function refreshDetail(id?: number) {
  const cid = id ?? detailModal.cable?.id
  const response = await request(`/api/cable/${cid}`)
  if (response.ok) {
    detailModal.cable = await response.json()
  } else {
    detailModal.open = false
    notify(false, '光缆明细读取失败')
  }
}
async function writeOffAt(cable: Row, seq: number) {
  try {
    const result = await apiPost(`/api/cable/${cable.id}/actions`, { action: '敷设核销', seq })
    notify(Boolean(result.ok), String(result.message))
    if (result.ok) {
      await Promise.all([refreshDetail(), reloadCables(), reloadLedger(), reloadStats()])
    }
  } catch (error) {
    notify(false, error instanceof Error ? error.message : '核销失败')
  }
}

const releaseModal = reactive<{ open: boolean; occ: Row | null; reason: string }>({
  open: false,
  occ: null,
  reason: '',
})
function openRelease(occ: Row) {
  releaseModal.occ = occ
  releaseModal.reason = ''
  releaseModal.open = true
}
async function submitRelease() {
  if (!releaseModal.reason.trim()) {
    notify(false, '请填写核销原因')
    return
  }
  try {
    const result = await apiPost(`/api/cable/occupancies/${releaseModal.occ?.id}/release`, {
      reason: releaseModal.reason.trim(),
    })
    notify(Boolean(result.ok), String(result.message))
    if (result.ok) {
      releaseModal.open = false
      await Promise.all([reloadCables(), reloadResources(), reloadLedger(), reloadStats(), refreshDetail()])
    }
  } catch (error) {
    notify(false, error instanceof Error ? error.message : '核销失败')
  }
}

// ---------- 孔位编辑 ----------
function addSlot(target: SlotDraft[]) {
  target.push({ 资源类型: '管道', 资源编码: '', 孔位: '' })
}
function removeSlot(target: SlotDraft[], index: number) {
  target.splice(index, 1)
}
function normalizeSlots(slots: SlotDraft[]): Row[] {
  return slots
    .filter((s) => s.资源类型 && s.资源编码 && s.孔位)
    .map((s) => ({ 资源类型: s.资源类型, 资源编码: s.资源编码, 孔位: s.孔位 }))
}

function exportRows() {
  window.open('/api/cable/export', '_blank')
}

// SlotEditor：内联小组件（管道/杆路 → 资源编码 → 孔位/杆位 三级联动）
const SlotEditor = defineComponent({
  name: 'SlotEditor',
  props: {
    slots: { type: Array as () => SlotDraft[], required: true },
    ducts: { type: Array as () => Row[], required: true },
    poles: { type: Array as () => Row[], required: true },
  },
  emits: ['add', 'remove'],
  setup(props, { emit }) {
    function resourceList(kind: string): Row[] {
      return kind === '管道' ? props.ducts : props.poles
    }
    function codeField(kind: string): string {
      return kind === '管道' ? '管道编号' : '杆路编号'
    }
    function posField(kind: string): string {
      return kind === '管道' ? '孔位列表' : '杆位列表'
    }
    function findResource(slot: SlotDraft): Row | undefined {
      return resourceList(slot.资源类型).find((r) => r[codeField(slot.资源类型)] === slot.资源编码)
    }
    function holeState(slot: SlotDraft, pos: string): Row | undefined {
      return findResource(slot)?.['孔位状态']?.find((h: Row) => h.孔位 === pos)
    }
    return () =>
      h('div', { class: 'slot-editor' }, [
        h('table', { class: 'data-table slot-table' }, [
          h('thead', {}, h('tr', {}, [
            h('th', {}, '敷设顺序'),
            h('th', {}, '资源类型'),
            h('th', {}, '资源编码'),
            h('th', {}, '孔位/杆位（占用情况）'),
            h('th', {}, ''),
          ])),
          h('tbody', {}, props.slots.map((slot, index) =>
            h('tr', {}, [
              h('td', {}, String(index + 1)),
              h('td', {}, h('select', {
                value: slot.资源类型,
                onChange: (e: Event) => {
                  slot.资源类型 = (e.target as HTMLSelectElement).value as '管道' | '杆路'
                  slot.资源编码 = ''
                  slot.孔位 = ''
                },
              }, [h('option', { value: '管道' }, '管道'), h('option', { value: '杆路' }, '杆路')])),
              h('td', {}, h('select', {
                value: slot.资源编码,
                onChange: (e: Event) => {
                  slot.资源编码 = (e.target as HTMLSelectElement).value
                  slot.孔位 = ''
                },
              }, [
                h('option', { value: '' }, '请选择'),
                ...resourceList(slot.资源类型).map((r) =>
                  h('option', { value: r[codeField(slot.资源类型)] }, String(r[codeField(slot.资源类型)]))),
              ])),
              h('td', {}, h('select', {
                value: slot.孔位,
                disabled: !slot.资源编码,
                onChange: (e: Event) => { slot.孔位 = (e.target as HTMLSelectElement).value },
              }, [
                h('option', { value: '' }, '请选择'),
                ...(findResource(slot)?.[posField(slot.资源类型)] ?? []).map((pos: string) => {
                  const state = holeState(slot, String(pos))
                  const label = state?.占用中
                    ? `${pos}（${state.历史 ? '历史占用' : '占用中'}：${state.占用光缆}）`
                    : `${pos}（空闲/可加挂）`
                  return h('option', { value: pos }, label)
                }),
              ])),
              h('td', {}, h('button', {
                class: 'link danger',
                type: 'button',
                onClick: () => emit('remove', index),
              }, '移除')),
            ]),
          )),
        ]),
        h('button', { class: 'btn ghost', type: 'button', onClick: () => emit('add') }, '+ 增加一处'),
      ])
  },
})

onMounted(async () => {
  await Promise.all([reloadCables(), reloadStats(), reloadResources()])
})
</script>

<style scoped>
.perm-hint {
  margin: 8px 0;
  padding: 6px 10px;
  background: #fff7ed;
  border: 1px solid #fdba74;
  border-radius: 6px;
  font-size: 13px;
  color: #9a3412;
}
.tab-bar { display: flex; gap: 8px; margin: 12px 0; border-bottom: 1px solid var(--border); }
.tab { border: none; background: none; padding: 8px 14px; cursor: pointer; font-size: 14px; color: var(--muted); border-bottom: 2px solid transparent; }
.tab.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.status-badge { padding: 2px 8px; border-radius: 10px; font-size: 12px; white-space: nowrap; }
.st-survey { background: #f1f5f9; color: #475569; }
.st-surveyed { background: #e0f2fe; color: #075985; }
.st-allocated { background: #fef9c3; color: #854d0e; }
.st-laid { background: #ffedd5; color: #9a3412; }
.st-verified { background: #dcfce7; color: #166534; }
.hole-used { color: #b42318; font-weight: 600; }
.hole-free { color: #166534; }
.resource-table { margin-bottom: 14px; }
.resource-table caption { text-align: left; font-weight: 600; padding: 6px 0; font-size: 13px; }
.audit-cell { font-size: 12px; color: var(--muted); white-space: nowrap; }
.muted-text { color: var(--muted); font-size: 12px; }
.link.danger { color: #b42318; }
.ok-text { color: #166534; }
.modal-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { background: #fff; border-radius: 10px; padding: 20px; width: 560px; max-width: 92vw; max-height: 88vh; overflow: auto; }
.modal-mask.wide .modal { width: 860px; }
.modal h3 { margin: 0 0 8px; }
.modal-tip { font-size: 12px; color: var(--muted); margin: 0 0 12px; line-height: 1.6; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.form-grid label span, .block-label span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.form-grid input, .block-label textarea { width: 100%; box-sizing: border-box; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.block-label { display: block; margin-top: 8px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.danger-btn { background: #b42318; border-color: #b42318; color: #fff; }
.slot-editor { margin-top: 8px; }
.slot-table { margin-bottom: 8px; }
.slot-table select { padding: 4px 6px; max-width: 220px; }
</style>
