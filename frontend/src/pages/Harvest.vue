<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'

const config = ref(null)
const dirInput = ref('')
const tasks = ref([])
const detail = ref(null)
const selectedId = ref(null)
const busy = ref(false)
const err = ref('')

const task = computed(() => detail.value?.task || null)
const rec = computed(() => detail.value?.reconciliation || null)
const checks = computed(() => rec.value?.checks || {})

function useDemo(name) {
  dirInput.value = name
}

function statusClass(status) {
  if (status === 'succeeded' || status === 'collected') return 'ok'
  if (status === 'partial' || status === 'skipped_duplicate' || status === 'empty') return 'warn'
  return 'danger'
}

async function loadTasks() {
  tasks.value = await getJSON('/api/harvest/tasks')
}

async function loadDetail(id) {
  if (!id) { detail.value = null; return }
  selectedId.value = id
  detail.value = await getJSON(`/api/harvest/tasks/${id}`)
}

async function loadConfig() {
  config.value = await getJSON('/api/harvest/config')
  if (!dirInput.value) dirInput.value = config.value.source_dir
}

async function startHarvest() {
  busy.value = true
  err.value = ''
  try {
    const body = {
      source_dir: dirInput.value,
      stream_id: config.value?.default_stream_id ?? null,
      auto_apply: true,
    }
    detail.value = await postJSON('/api/harvest/tasks', body)
    selectedId.value = detail.value.task.id
    await loadTasks()
    await loadConfig()
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function applyTask(id) {
  busy.value = true
  err.value = ''
  try {
    detail.value = await postJSON(`/api/harvest/tasks/${id}/apply`, {})
    selectedId.value = detail.value.task.id
    await loadTasks()
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function openTask(t) {
  err.value = ''
  try { await loadDetail(t.id) } catch (e) { err.value = String(e.message || e) }
}

onMounted(async () => {
  try {
    await loadConfig()
    await loadTasks()
    if (tasks.value.length) await loadDetail(tasks.value[0].id)
  } catch (e) {
    err.value = String(e.message || e)
  }
})
</script>

<template>
  <div class="page">
    <h1>采集巡检</h1>
    <p class="muted">
      巡检本机 CDC 目录 → 生成采集任务与分片清单 → 分片事件入账 → 按连续序 Apply。
      采集不直接写 Sink；缺口仍走隔离区。
    </p>

    <p v-if="err" class="tag danger">{{ err }}</p>

    <div class="panel">
      <h3>发起巡检</h3>
      <div class="row-actions">
        <label class="grow">目录
          <input v-model="dirInput" placeholder="harvest_demo 或本机绝对路径" style="min-width: 22rem" />
        </label>
        <button :disabled="busy" @click="startHarvest">{{ busy ? '采集中…' : '巡检并采集' }}</button>
      </div>
      <p class="muted" v-if="config">
        可用演示目录：
        <a v-for="d in config.demo_dirs" :key="d" href="#" @click.prevent="useDemo(d)" class="demo-link">fixtures/{{ d }}</a>
        <span class="muted">· 只允许本机目录：{{ config.allowed_roots.join('、') }} · 分片后缀 {{ config.suffixes.join(' ') }}</span>
      </p>
      <p class="muted" v-if="config">同名同内容分片策略：{{ config.dupe_policy }}（跳过并记录 duplicate_of）</p>
    </div>

    <div class="panel">
      <h3>采集任务</h3>
      <table>
        <thead>
          <tr><th>ID</th><th>目录</th><th>状态</th><th>发现</th><th>成功</th><th>跳过</th><th>失败</th><th>入账事件</th><th>Apply run</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="t in tasks" :key="t.id" class="clickable" :class="{ selected: t.id === selectedId }" @click="openTask(t)">
            <td>{{ t.id }}</td>
            <td><code>{{ t.source_dir }}</code></td>
            <td><span class="tag" :class="statusClass(t.status)">{{ t.status }}</span></td>
            <td>{{ t.discovered_count }}</td>
            <td>{{ t.success_count }}</td>
            <td>{{ t.skipped_count }}</td>
            <td>{{ t.failed_count }}</td>
            <td>{{ t.event_count }}</td>
            <td>{{ t.apply_run_id ?? '—' }}</td>
            <td>{{ t.created_at }}</td>
          </tr>
          <tr v-if="!tasks.length"><td colspan="10" class="muted">还没有采集任务，先发起一次巡检。</td></tr>
        </tbody>
      </table>
    </div>

    <div v-if="detail" class="panel">
      <div class="row-actions" style="justify-content: space-between">
        <h3>任务 #{{ task.id }} 对账</h3>
        <button v-if="rec.not_yet_applied > 0 || !rec.apply_runs.length" :disabled="busy" @click="applyTask(task.id)">
          {{ busy ? '应用中…' : '重试未应用事件' }}
        </button>
      </div>

      <div class="tiles">
        <div class="tile"><div class="hero-num">{{ rec.discovered_files }}</div><div class="muted">发现分片</div></div>
        <div class="tile"><div class="hero-num">{{ rec.collected_files }}</div><div class="muted">采集成功</div></div>
        <div class="tile"><div class="hero-num">{{ rec.skipped_files }}</div><div class="muted">跳过（重复）</div></div>
        <div class="tile"><div class="hero-num">{{ rec.failed_files }}</div><div class="muted">失败分片</div></div>
        <div class="tile"><div class="hero-num">{{ rec.collected_events }}</div><div class="muted">入账事件</div></div>
        <div class="tile"><div class="hero-num">{{ rec.applied }}</div><div class="muted">applied</div></div>
        <div class="tile"><div class="hero-num">{{ rec.quarantined }}</div><div class="muted">quarantined</div></div>
        <div class="tile"><div class="hero-num">{{ rec.skipped_duplicate }}</div><div class="muted">skipped 重复</div></div>
        <div class="tile"><div class="hero-num">{{ rec.not_yet_applied }}</div><div class="muted">待应用</div></div>
        <div class="tile"><div class="hero-num">{{ rec.sink_rows_for_stream }}</div><div class="muted">Sink 行（本流）</div></div>
      </div>

      <p>
        对账结论：
        <span class="tag" :class="rec.balanced ? 'ok' : 'danger'">{{ rec.balanced ? '各项一致' : '存在不一致' }}</span>
        · 账本事件 {{ rec.ledger_events }} · 流游标 {{ rec.stream_cursor_after }} · Sink 变化 {{ rec.sink_delta_from_runs }}
      </p>
      <ul class="checks">
        <li v-for="(ok, name) in checks" :key="name">
          <span class="tag" :class="ok ? 'ok' : 'danger'">{{ ok ? 'OK' : '不一致' }}</span>
          <code>{{ name }}</code>
        </li>
      </ul>

      <h4>分片清单</h4>
      <table>
        <thead>
          <tr><th>ID</th><th>相对路径</th><th>状态</th><th>事件</th><th>seq 范围</th><th>大小</th><th>sha256</th><th>说明</th><th>dup of</th></tr>
        </thead>
        <tbody>
          <tr v-for="s in detail.shards" :key="s.id">
            <td>{{ s.id }}</td>
            <td><code>{{ s.rel_path }}</code></td>
            <td><span class="tag" :class="statusClass(s.status)">{{ s.status }}</span></td>
            <td>{{ s.event_count }}</td>
            <td>{{ s.first_seq ?? '—' }}→{{ s.last_seq ?? '—' }}</td>
            <td>{{ s.size_bytes }}</td>
            <td><code>{{ s.sha256.slice(0, 12) }}…</code></td>
            <td class="muted">{{ s.reason || '—' }}</td>
            <td>{{ s.duplicate_of ?? '—' }}</td>
          </tr>
        </tbody>
      </table>

      <h4>Apply 明细</h4>
      <table>
        <thead>
          <tr><th>run</th><th>状态</th><th>loaded</th><th>applied</th><th>quarantined</th><th>skipped</th><th>cursor</th><th>Sink 变化</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rec.apply_runs" :key="r.run_id">
            <td>#{{ r.run_id }}</td>
            <td><span class="tag" :class="statusClass(r.status)">{{ r.status }}</span></td>
            <td>{{ r.loaded }}</td>
            <td>{{ r.applied }}</td>
            <td>{{ r.quarantined }}</td>
            <td>{{ r.skipped }}</td>
            <td>{{ r.cursor_before }}→{{ r.cursor_after }}</td>
            <td>{{ r.sink_delta ?? '—' }}</td>
            <td>{{ r.created_at }}</td>
          </tr>
          <tr v-if="!rec.apply_runs.length"><td colspan="9" class="muted">尚未应用（或全部为重复跳过）</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
