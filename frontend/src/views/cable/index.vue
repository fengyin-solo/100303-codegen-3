<template>
  <section class="page" data-module="cable">
    <header class="page-head">
      <div>
        <h2>光缆段台账</h2>
        <p class="page-desc">
          按起点、终点与占用管道孔位/杆路挂点登记光缆段；一孔不挂两缆，冲突挡下并指明占用方。
          加挂沿 勘测→已分配→已敷设→已核实 推进，敷设中断从断点孔位续核销。
        </p>
      </div>
      <div class="identity-box">
        <label class="identity-item">
          <span>当前身份</span>
          <select :value="`${store.teamId}|${store.role}`" @change="onSwitchIdentity">
            <option v-for="item in store.teams" :key="`${item.teamId}-${item.role}`" :value="`${item.teamId}|${item.role}`">
              {{ item.teamName }} · {{ item.role }}
            </option>
          </select>
        </label>
        <span class="identity-tag" :class="{ readonly: !store.canWriteCable }">
          {{ store.canWriteCable ? '可核销（本队资料员）' : '只读视角' }}
        </span>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="tab-bar">
      <button v-for="tab in tabs" :key="tab.key" class="tab-btn" :class="{ active: activeTab === tab.key }" type="button" @click="switchTab(tab.key)">
        {{ tab.label }}
      </button>
    </nav>

    <!-- ===================== 光缆段 ===================== -->
    <div v-if="activeTab === 'segments'">
      <form class="filter-bar" @submit.prevent="reloadSegments">
        <label class="filter-item"><span>关键词</span><input v-model="segFilter.keyword" placeholder="编号/起点/终点" /></label>
        <label class="filter-item"><span>阶段</span>
          <select v-model="segFilter.status">
            <option value="">全部</option>
            <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <label class="filter-item"><span>敷设方式</span>
          <select v-model="segFilter.layWay">
            <option value="">全部</option>
            <option value="管道">管道</option>
            <option value="杆路">杆路</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn primary" type="button" :disabled="!store.canWriteCable" @click="openRegister">登记光缆段（勘测）</button>
        <button class="btn" type="button" :disabled="!store.canWriteCable" @click="openLegacy">存量光缆补登</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>光缆段编号</th><th>起点</th><th>终点</th><th>敷设方式</th><th>型号/芯数</th>
            <th>阶段</th><th>孔位进度</th><th>断点孔位</th><th>归属</th><th>来源</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in segments" :key="String(row.id)">
            <td>{{ row['光缆段编号'] }}</td>
            <td>{{ row['起点'] }}</td><td>{{ row['终点'] }}</td>
            <td>{{ row['敷设方式'] }}</td>
            <td>{{ row['光缆型号'] }} / {{ row['芯数'] }}芯</td>
            <td><span class="stage-badge" :class="stageClass(row.status)">{{ row.status }}</span></td>
            <td>{{ row['已核销数'] }}/{{ row['孔位总数'] }}（已分配待核销 {{ row['已分配数'] }}）</td>
            <td>{{ formatHole(row['断点孔位']) || '—' }}</td>
            <td>{{ row['施工队'] }}</td>
            <td>{{ row['历史遗留'] ? '存量补登' : '新工登记' }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="openDetail(row)">明细</button>
              <button v-if="row.status === '勘测' && canWrite(row)" class="link" type="button" @click="allocate(row)">分配孔位</button>
              <button v-if="['已分配', '已敷设'].includes(row.status) && row['已分配数'] > 0 && canWrite(row)" class="link" type="button" @click="openWriteOff(row)">
                敷设核销{{ row['已核销数'] === 0 ? '' : '（断点续敷）' }}
              </button>
              <button v-if="row.status === '已敷设' && canWrite(row)" class="link" type="button" @click="verify(row)">核实</button>
              <button v-if="!row['历史遗留'] && canWrite(row)" class="link danger" type="button" @click="openRelease(row)">撤占核销</button>
            </td>
          </tr>
          <tr v-if="!segments.length">
            <td colspan="11" class="empty-state">暂无符合条件的光缆段</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot">
        <span>共 {{ segTotal }} 条光缆段</span>
        <span v-if="message" class="error-text">{{ message }}</span>
      </footer>
    </div>

    <!-- ===================== 占用核销台账 ===================== -->
    <div v-if="activeTab === 'occupancy'">
      <form class="filter-bar" @submit.prevent="reloadOccupancy">
        <label class="filter-item"><span>资源编号</span><input v-model="occFilter.resourceCode" placeholder="如 GD-城东-01" /></label>
        <label class="filter-item"><span>占用状态</span>
          <select v-model="occFilter.status">
            <option value="">全部</option>
            <option value="已分配">已分配（待核销）</option>
            <option value="已核销">已核销</option>
            <option value="已释放">已释放</option>
          </select>
        </label>
        <label class="filter-item"><span>关键词</span><input v-model="occFilter.keyword" placeholder="光缆段/资源" /></label>
        <button class="btn" type="submit">查询</button>
      </form>
      <table class="data-table">
        <thead>
          <tr><th>顺序</th><th>资源类型</th><th>资源编号</th><th>孔位/挂点</th><th>占用光缆段</th><th>状态</th><th>来源</th><th>归属施工队</th><th>释放备注</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in occupancyRows" :key="String(row.id)">
            <td>{{ row['顺序'] + 1 }}</td>
            <td>{{ row['资源类型'] }}</td>
            <td>{{ row['资源编号'] }}</td>
            <td>{{ row['孔位'] }}</td>
            <td>{{ row['光缆段编号'] }}</td>
            <td><span class="stage-badge" :class="occClass(row['状态'])">{{ row['状态'] }}</span></td>
            <td>{{ row['历史遗留'] ? '历史遗留' : '新工' }}</td>
            <td>{{ row['施工队'] }}</td>
            <td>{{ row['释放备注'] || '—' }}</td>
          </tr>
          <tr v-if="!occupancyRows.length"><td colspan="9" class="empty-state">暂无占用记录</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ===================== 资源余量 ===================== -->
    <div v-if="activeTab === 'resources'">
      <form class="filter-bar" @submit.prevent="reloadResources">
        <label class="filter-item"><span>资源类型</span>
          <select v-model="resFilter" @change="reloadResources">
            <option value="">全部</option><option value="管道">管道</option><option value="杆路">杆路</option>
          </select>
        </label>
        <button class="btn primary" type="button" :disabled="!store.canWriteCable" @click="openResource">登记资源容量</button>
      </form>
      <table class="data-table">
        <thead>
          <tr><th>类型</th><th>资源编号</th><th>资源名称</th><th>容量（孔/挂点）</th><th>活跃占用</th><th>剩余</th><th>归属</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in resourceRows" :key="String(row.id)">
            <td>{{ row['资源类型'] }}</td>
            <td>{{ row['资源编号'] }}</td>
            <td>{{ row['资源名称'] }}</td>
            <td>{{ row['容量'] ?? '容量未登记' }}</td>
            <td>{{ row['占用孔位数'] }}</td>
            <td>
              <span :class="{ 'error-text': row['剩余孔位数'] === 0 }">
                {{ row['剩余孔位数'] ?? '—' }}
              </span>
            </td>
            <td>{{ row['施工队'] }}</td>
          </tr>
          <tr v-if="!resourceRows.length"><td colspan="7" class="empty-state">暂无资源</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ===================== 弹窗：登记 ===================== -->
    <div v-if="registerOpen" class="modal-mask" @click.self="registerOpen = false">
      <div class="modal">
        <h3>登记光缆段（勘测）</h3>
        <div class="form-grid">
          <label><span>光缆段编号（可空）</span><input v-model="regForm.code" placeholder="留空自动编号" /></label>
          <label><span>起点 *</span><input v-model="regForm.start" /></label>
          <label><span>终点 *</span><input v-model="regForm.end" /></label>
          <label><span>敷设方式 *</span>
            <select v-model="regForm.layWay"><option value="管道">管道</option><option value="杆路">杆路</option></select>
          </label>
          <label><span>光缆型号</span><input v-model="regForm.model" /></label>
          <label><span>芯数</span><input v-model.number="regForm.fibers" type="number" min="0" /></label>
        </div>
        <div class="hole-editor">
          <div class="hole-head">
            <strong>计划占用孔位（按敷设顺序）*</strong>
            <button class="btn" type="button" @click="addRegHole">加一个孔位</button>
          </div>
          <table class="data-table">
            <thead><tr><th>顺序</th><th>资源编号</th><th>孔位/挂点</th><th></th></tr></thead>
            <tbody>
              <tr v-for="(hole, idx) in regForm.holes" :key="idx">
                <td>{{ idx + 1 }}</td>
                <td><input v-model="hole.resourceCode" placeholder="GD-城东-01 / GG-001" /></td>
                <td><input v-model="hole.hole" placeholder="1#孔 / 第1挂点" /></td>
                <td><button class="link danger" type="button" @click="regForm.holes.splice(idx, 1)">删除</button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="modal-tip">同一起点+终点+敷设方式重复登记只记一次；孔位在「分配」时统一做互斥校验。</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="registerOpen = false">取消</button>
          <button class="btn primary" type="button" @click="submitRegister">提交登记</button>
        </div>
      </div>
    </div>

    <!-- ===================== 弹窗：敷设核销 ===================== -->
    <div v-if="writeOffOpen" class="modal-mask" @click.self="writeOffOpen = false">
      <div class="modal">
        <h3>敷设核销 · {{ writeOffTarget?.['光缆段编号'] }}</h3>
        <p class="modal-tip">
          已核销 {{ writeOffTarget?.['已核销数'] }}/{{ writeOffTarget?.['孔位总数'] }}；
          断点在 <strong>{{ formatHole(writeOffTarget?.['断点孔位']) || '无' }}</strong>，
          只能从断点开始按序核销，已核销孔位不会重复扣。
        </p>
        <table class="data-table">
          <thead><tr><th>顺序</th><th>资源</th><th>孔位</th><th>当前状态</th><th>本次核销</th></tr></thead>
          <tbody>
            <tr v-for="occ in writeOffTarget?.['占用明细']" :key="String(occ.id)"
                :class="{ disabled: occ['状态'] === '已释放' }">
              <td>{{ occ['顺序'] + 1 }}</td>
              <td>{{ occ['资源编号'] }}</td><td>{{ occ['孔位'] }}</td>
              <td>{{ occ['状态'] }}</td>
              <td><input type="checkbox" :checked="writeOffChecked.has(String(occ.id))" :disabled="occ['状态'] !== '已分配'" @change="toggleWriteOff(occ)" /></td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn" type="button" @click="writeOffOpen = false">取消</button>
          <button class="btn primary" type="button" @click="submitWriteOff">提交核销</button>
        </div>
      </div>
    </div>

    <!-- ===================== 弹窗：撤占核销 ===================== -->
    <div v-if="releaseOpen" class="modal-mask" @click.self="releaseOpen = false">
      <div class="modal">
        <h3>撤占核销 · {{ releaseTarget?.['光缆段编号'] }}</h3>
        <p class="modal-tip">释放后孔位立刻可被其他光缆段占用；请填写撤占原因。</p>
        <table class="data-table">
          <thead><tr><th>资源</th><th>孔位</th><th>状态</th><th>释放</th></tr></thead>
          <tbody>
            <tr v-for="occ in activeOccOfRelease" :key="String(occ.id)">
              <td>{{ occ['资源编号'] }}</td><td>{{ occ['孔位'] }}</td><td>{{ occ['状态'] }}</td>
              <td><input type="checkbox" :checked="releaseChecked.has(String(occ.id))" @change="toggleRelease(occ)" /></td>
            </tr>
          </tbody>
        </table>
        <label class="remark-line"><span>撤装备注</span><input v-model="releaseRemark" placeholder="如：割接改路，撤占" /></label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="releaseOpen = false">取消</button>
          <button class="btn primary" type="button" @click="submitRelease">确认释放</button>
        </div>
      </div>
    </div>

    <!-- ===================== 弹窗：明细 ===================== -->
    <div v-if="detailOpen" class="modal-mask" @click.self="detailOpen = false">
      <div class="modal wide">
        <h3>{{ detailRow?.['光缆段编号'] }}（{{ detailRow?.['起点'] }} → {{ detailRow?.['终点'] }}）</h3>
        <table class="data-table">
          <thead><tr><th>顺序</th><th>资源类型</th><th>资源</th><th>孔位</th><th>占用状态</th><th>来源</th><th>备注</th></tr></thead>
          <tbody>
            <tr v-for="occ in detailRow?.['占用明细']" :key="String(occ.id)">
              <td>{{ occ['顺序'] + 1 }}</td><td>{{ occ['资源类型'] }}</td><td>{{ occ['资源编号'] }}</td>
              <td>{{ occ['孔位'] }}</td><td>{{ occ['状态'] }}</td>
              <td>{{ occ['历史遗留'] ? '历史遗留' : '新工' }}</td><td>{{ occ['释放备注'] || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions"><button class="btn primary" type="button" @click="detailOpen = false">关闭</button></div>
      </div>
    </div>

    <!-- ===================== 弹窗：存量补登 ===================== -->
    <div v-if="legacyOpen" class="modal-mask" @click.self="legacyOpen = false">
      <div class="modal wide">
        <h3>存量光缆补登</h3>
        <p class="modal-tip">按敷设顺序把存量光缆的杆路挂点/管道孔位整段写入；占用一律标记「历史遗留」按原登记保留，不做互斥拦截，整段任一缺项则整批挡下。</p>
        <div class="legacy-editor">
          <div v-for="(cable, ci) in legacyForm.cables" :key="ci" class="legacy-card">
            <div class="form-grid">
              <label><span>编号</span><input v-model="cable.code" /></label>
              <label><span>起点 *</span><input v-model="cable.start" /></label>
              <label><span>终点 *</span><input v-model="cable.end" /></label>
              <label><span>方式 *</span><select v-model="cable.layWay"><option value="管道">管道</option><option value="杆路">杆路</option></select></label>
            </div>
            <table class="data-table">
              <thead><tr><th>顺序</th><th>资源编号</th><th>孔位</th><th></th></tr></thead>
              <tbody>
                <tr v-for="(hole, hi) in cable.holes" :key="hi">
                  <td>{{ hi + 1 }}</td>
                  <td><input v-model="hole.resourceCode" /></td>
                  <td><input v-model="hole.hole" /></td>
                  <td><button class="link danger" type="button" @click="cable.holes.splice(hi, 1)">删除</button></td>
                </tr>
              </tbody>
            </table>
            <button class="btn" type="button" @click="cable.holes.push({ resourceCode: '', hole: '' })">加孔位</button>
            <button class="link danger legacy-remove" type="button" @click="legacyForm.cables.splice(ci, 1)">删除该段</button>
          </div>
        </div>
        <button class="btn" type="button" @click="addLegacyCable">再加一段存量光缆</button>
        <div class="modal-actions">
          <button class="btn" type="button" @click="legacyOpen = false">取消</button>
          <button class="btn primary" type="button" @click="submitLegacy">整批补登</button>
        </div>
      </div>
    </div>

    <!-- ===================== 弹窗：资源容量 ===================== -->
    <div v-if="resourceOpen" class="modal-mask" @click.self="resourceOpen = false">
      <div class="modal">
        <h3>登记管道/杆路资源</h3>
        <div class="form-grid">
          <label><span>资源类型 *</span><select v-model="resForm.resourceType"><option value="管道">管道</option><option value="杆路">杆路</option></select></label>
          <label><span>资源编号 *</span><input v-model="resForm.code" placeholder="GD-xxx / GG-xxx" /></label>
          <label><span>资源名称</span><input v-model="resForm.name" /></label>
          <label><span>孔位容量</span><input v-model.number="resForm.capacity" type="number" min="0" placeholder="如 6" /></label>
        </div>
        <div class="modal-actions">
          <button class="btn" type="button" @click="resourceOpen = false">取消</button>
          <button class="btn primary" type="button" @click="submitResource">保存</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const STATUSES = ['勘测', '已分配', '已敷设', '已核实']

type Hole = { resourceCode: string; hole: string }
type SegmentRow = Record<string, any>
type OccRow = Record<string, any>

const activeTab = ref<'segments' | 'occupancy' | 'resources'>('segments')
const tabs = [
  { key: 'segments' as const, label: '光缆段台账' },
  { key: 'occupancy' as const, label: '占用核销' },
  { key: 'resources' as const, label: '管道/杆路资源余量' },
]
const message = ref('')

const stats = ref<Record<string, number>>({})
const statCards = computed(() => [
  { label: '光缆段总数', value: stats.value['光缆段总数'] ?? 0 },
  { label: '勘测中', value: stats.value['勘测中'] ?? 0 },
  { label: '已分配待敷设', value: stats.value['已分配待敷设'] ?? 0 },
  { label: '已敷设待核实', value: stats.value['已敷设待核实'] ?? 0 },
  { label: '待核销孔位', value: stats.value['待核销孔位'] ?? 0 },
  { label: '历史遗留占用', value: stats.value['历史遗留占用'] ?? 0 },
])

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return {
    'X-Team-Id': store.teamId,
    'X-Team-Name': store.teamName,
    'X-Role': store.role,
    ...extra,
  }
}

async function postJson(path: string, body: unknown): Promise<{ ok: boolean; message: string; entry: any }> {
  const response = await request(path, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ values: body }),
  })
  return response.json()
}

function canWrite(row: SegmentRow): boolean {
  return store.canWriteCable && row['team_id'] === store.teamId
}

function formatHole(hole: any): string {
  return hole ? `${hole['资源编号']}/${hole['孔位']}` : ''
}

function stageClass(status: string): string {
  return { 勘测: 'st-survey', 已分配: 'st-allocated', 已敷设: 'st-laid', 已核实: 'st-done' }[status] ?? ''
}
function occClass(status: string): string {
  return { 已分配: 'st-allocated', 已核销: 'st-done', 已释放: 'st-released' }[status] ?? ''
}

function onSwitchIdentity(event: Event) {
  const [teamId, role] = (event.target as HTMLSelectElement).value.split('|')
  store.switchProfile(teamId, role)
  void reloadAll()
}

// --------------------------- 光缆段列表 ---------------------------
const segments = ref<SegmentRow[]>([])
const segTotal = ref(0)
const segFilter = reactive({ keyword: '', status: '', layWay: '' })

async function reloadSegments() {
  const query = new URLSearchParams()
  if (segFilter.keyword) query.set('keyword', segFilter.keyword)
  if (segFilter.status) query.set('status', segFilter.status)
  if (segFilter.layWay) query.set('lay_way', segFilter.layWay)
  const response = await request(`/api/cable/segments?${query.toString()}`)
  const payload = await response.json()
  segments.value = payload.items ?? []
  segTotal.value = payload.total ?? 0
}

async function allocate(row: SegmentRow) {
  message.value = ''
  const result = await postJson(`/api/cable/segments/${row.id}/allocate`, {})
  message.value = result.message
  await reloadAll()
}

async function verify(row: SegmentRow) {
  message.value = ''
  const result = await postJson(`/api/cable/segments/${row.id}/verify`, {})
  message.value = result.message
  await reloadAll()
}

// --------------------------- 占用/资源 ---------------------------
const occupancyRows = ref<OccRow[]>([])
const occFilter = reactive({ resourceCode: '', status: '', keyword: '' })
async function reloadOccupancy() {
  const query = new URLSearchParams()
  if (occFilter.resourceCode) query.set('resource_code', occFilter.resourceCode)
  if (occFilter.status) query.set('status', occFilter.status)
  if (occFilter.keyword) query.set('keyword', occFilter.keyword)
  const response = await request(`/api/cable/occupancy?${query.toString()}`)
  const payload = await response.json()
  occupancyRows.value = payload.items ?? []
}

const resourceRows = ref<Record<string, any>[]>([])
const resFilter = ref('')
async function reloadResources() {
  const query = new URLSearchParams()
  if (resFilter.value) query.set('resource_type', resFilter.value)
  const response = await request(`/api/cable/resources?${query.toString()}`)
  const payload = await response.json()
  resourceRows.value = payload.items ?? []
}

async function reloadStats() {
  const response = await request('/api/cable/stats')
  stats.value = await response.json()
}

function switchTab(key: 'segments' | 'occupancy' | 'resources') {
  activeTab.value = key
  message.value = ''
  void reloadAll()
}

async function reloadAll() {
  await Promise.all([reloadStats(), reloadSegments(), reloadOccupancy(), reloadResources()])
}

// --------------------------- 登记弹窗 ---------------------------
const registerOpen = ref(false)
const regForm = reactive({ code: '', start: '', end: '', layWay: '管道', model: '', fibers: 24, holes: [] as Hole[] })

function openRegister() {
  Object.assign(regForm, { code: '', start: '', end: '', layWay: '管道', model: '', fibers: 24, holes: [{ resourceCode: '', hole: '' }] })
  registerOpen.value = true
}
function addRegHole() {
  regForm.holes.push({ resourceCode: '', hole: '' })
}
async function submitRegister() {
  message.value = ''
  const result = await postJson('/api/cable/segments', {
    光缆段编号: regForm.code, 起点: regForm.start, 终点: regForm.end, 敷设方式: regForm.layWay,
    光缆型号: regForm.model, 芯数: regForm.fibers,
    孔位序列: regForm.holes.map((h, idx) => ({ 资源类型: regForm.layWay, 资源编号: h.resourceCode, 孔位: h.hole, 顺序: idx })),
  })
  message.value = result.message
  if (result.ok) {
    registerOpen.value = false
    await reloadAll()
  }
}

// --------------------------- 敷设核销弹窗 ---------------------------
const writeOffOpen = ref(false)
const writeOffTarget = ref<SegmentRow | null>(null)
const writeOffChecked = ref<Set<string>>(new Set())

async function openWriteOff(row: SegmentRow) {
  const response = await request(`/api/cable/segments/${row.id}`)
  writeOffTarget.value = await response.json()
  writeOffChecked.value = new Set()
  writeOffOpen.value = true
}
function toggleWriteOff(occ: OccRow) {
  const id = String(occ.id)
  writeOffChecked.value.has(id) ? writeOffChecked.value.delete(id) : writeOffChecked.value.add(id)
}
async function submitWriteOff() {
  if (!writeOffTarget.value) return
  const chosen = writeOffTarget.value['占用明细']
    .filter((occ: OccRow) => writeOffChecked.value.has(String(occ.id)))
    .map((occ: OccRow) => ({ 资源编号: occ['资源编号'], 孔位: occ['孔位'] }))
  if (!chosen.length) {
    message.value = '请勾选本次要核销的孔位（从断点开始）'
    return
  }
  const result = await postJson(`/api/cable/segments/${writeOffTarget.value.id}/write-off`, { 孔位: chosen })
  message.value = result.message
  writeOffOpen.value = false
  await reloadAll()
}

// --------------------------- 撤占核销弹窗 ---------------------------
const releaseOpen = ref(false)
const releaseTarget = ref<SegmentRow | null>(null)
const releaseChecked = ref<Set<string>>(new Set())
const releaseRemark = ref('')
const activeOccOfRelease = computed(() => (releaseTarget.value?.['占用明细'] ?? []).filter((occ: OccRow) => occ['状态'] !== '已释放'))

async function openRelease(row: SegmentRow) {
  const response = await request(`/api/cable/segments/${row.id}`)
  releaseTarget.value = await response.json()
  releaseChecked.value = new Set()
  releaseRemark.value = ''
  releaseOpen.value = true
}
function toggleRelease(occ: OccRow) {
  const id = String(occ.id)
  releaseChecked.value.has(id) ? releaseChecked.value.delete(id) : releaseChecked.value.add(id)
}
async function submitRelease() {
  if (!releaseTarget.value) return
  const holes = releaseTarget.value['占用明细']
    .filter((occ: OccRow) => releaseChecked.value.has(String(occ.id)))
    .map((occ: OccRow) => ({ 资源编号: occ['资源编号'], 孔位: occ['孔位'] }))
  if (!holes.length) {
    message.value = '请勾选要释放的孔位'
    return
  }
  const result = await postJson(`/api/cable/segments/${releaseTarget.value.id}/release`, { 孔位: holes, remark: releaseRemark.value })
  message.value = result.message
  releaseOpen.value = false
  await reloadAll()
}

// --------------------------- 明细弹窗 ---------------------------
const detailOpen = ref(false)
const detailRow = ref<SegmentRow | null>(null)
async function openDetail(row: SegmentRow) {
  const response = await request(`/api/cable/segments/${row.id}`)
  detailRow.value = await response.json()
  detailOpen.value = true
}

// --------------------------- 存量补登弹窗 ---------------------------
const legacyOpen = ref(false)
type LegacyCable = { code: string; start: string; end: string; layWay: string; holes: Hole[] }
const legacyForm = reactive({ cables: [] as LegacyCable[] })

function addLegacyCable() {
  legacyForm.cables.push({ code: '', start: '', end: '', layWay: '管道', holes: [{ resourceCode: '', hole: '' }] })
}
function openLegacy() {
  legacyForm.cables = []
  addLegacyCable()
  legacyOpen.value = true
}
async function submitLegacy() {
  message.value = ''
  const result = await postJson('/api/cable/legacy-import', {
    光缆段: legacyForm.cables.map((c) => ({
      光缆段编号: c.code || undefined, 起点: c.start, 终点: c.end, 敷设方式: c.layWay,
      孔位序列: c.holes.map((h, hi) => ({ 资源类型: c.layWay, 资源编号: h.resourceCode, 孔位: h.hole, 顺序: hi })),
    })),
  })
  message.value = result.message
  if (result.ok) {
    legacyOpen.value = false
    await reloadAll()
  }
}

// --------------------------- 资源容量弹窗 ---------------------------
const resourceOpen = ref(false)
const resForm = reactive({ resourceType: '管道', code: '', name: '', capacity: 6 })
function openResource() {
  Object.assign(resForm, { resourceType: '管道', code: '', name: '', capacity: 6 })
  resourceOpen.value = true
}
async function submitResource() {
  message.value = ''
  const result = await postJson('/api/cable/resources', {
    资源类型: resForm.resourceType, 资源编号: resForm.code, 资源名称: resForm.name, 容量: resForm.capacity,
  })
  message.value = result.message
  if (result.ok) {
    resourceOpen.value = false
    await reloadResources()
  }
}

onMounted(reloadAll)
</script>

<style scoped>
.identity-box { display: flex; align-items: center; gap: 10px; }
.identity-item span { display: block; font-size: 12px; color: var(--muted); }
.identity-tag { font-size: 12px; padding: 4px 8px; border-radius: 999px; background: #dcfae6; color: #067647; }
.identity-tag.readonly { background: #f2f4f7; color: #667085; }

.tab-bar { display: flex; gap: 6px; margin: 8px 0 12px; }
.tab-btn { border: 1px solid var(--border); background: #fff; border-radius: 6px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
.tab-btn.active { background: var(--brand); color: #fff; border-color: var(--brand); }

.stage-badge { padding: 2px 8px; border-radius: 999px; font-size: 12px; }
.st-survey { background: #eef4ff; color: #1849a9; }
.st-allocated { background: #fffaeb; color: #b54708; }
.st-laid { background: #f4ebff; color: #6941c6; }
.st-done { background: #dcfae6; color: #067647; }
.st-released { background: #f2f4f7; color: #667085; }
.link.danger { color: #b42318; }
tr.disabled { opacity: 0.5; }

.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: flex-start; justify-content: center; padding: 32px 16px; overflow-y: auto; z-index: 50; }
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 640px; max-width: 100%; }
.modal.wide { width: 920px; }
.modal h3 { margin: 0 0 10px; font-size: 16px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
.form-grid label span, .remark-line span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
input, select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; min-width: 0; }
.form-grid input, .form-grid select { width: 100%; box-sizing: border-box; }
.hole-editor { margin: 8px 0; }
.hole-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.hole-editor input, .legacy-card input { width: 92%; }
.modal-tip { font-size: 12px; color: var(--muted); background: #f9fafb; border-radius: 6px; padding: 8px 10px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.remark-line { display: block; margin-top: 10px; }
.remark-line input { width: 100%; box-sizing: border-box; }
.legacy-card { border: 1px solid var(--border); border-radius: 8px; padding: 10px; margin-bottom: 10px; }
.legacy-remove { margin-left: 10px; }
</style>
