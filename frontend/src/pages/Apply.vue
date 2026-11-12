<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'
const streams = ref([])
const streamId = ref(1)
const last = ref(null)
const runs = ref([])
const err = ref('')
const busy = ref(false)
async function refreshRuns() {
  runs.value = await getJSON('/api/runs')
}
async function runApply() {
  busy.value = true
  err.value = ''
  try {
    last.value = await postJSON('/api/apply', { stream_id: streamId.value })
    streams.value = await getJSON('/api/streams')
    await refreshRuns()
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  streams.value = await getJSON('/api/streams')
  if (streams.value.length) streamId.value = streams.value[0].id
  await refreshRuns()
})
</script>
<template>
  <div class="page">
    <h1>应用台</h1>
    <p class="muted">按游标连续序应用；缺口默认停并进隔离区。</p>
    <div class="row-actions panel">
      <label>流
        <select v-model.number="streamId">
          <option v-for="s in streams" :key="s.id" :value="s.id">{{ s.id }} · {{ s.name }}（游标 {{ s.apply_cursor }}）</option>
        </select>
      </label>
      <button :disabled="busy" @click="runApply">{{ busy ? '应用中…' : '执行 Apply' }}</button>
    </div>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel" v-if="last">
      <h3>最近一次</h3>
      <p>
        run #{{ last.id }} ·
        <span class="tag" :class="last.status === 'succeeded' ? 'ok' : 'warn'">{{ last.status }}</span>
        · loaded {{ last.loaded_count }} / applied {{ last.applied_count }} /
        quarantined {{ last.quarantined_count }} / skipped {{ last.skipped_count }}
        · cursor {{ last.cursor_before }} → {{ last.cursor_after }}
      </p>
      <pre class="mono">{{ JSON.stringify(last.report, null, 2) }}</pre>
    </div>
    <div class="panel">
      <h3>历史 Runs</h3>
      <table>
        <thead>
          <tr><th>ID</th><th>流</th><th>状态</th><th>loaded</th><th>applied</th><th>quarantine</th><th>skipped</th><th>cursor</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in runs" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.stream_id }}</td>
            <td>{{ r.status }}</td>
            <td>{{ r.loaded_count }}</td>
            <td>{{ r.applied_count }}</td>
            <td>{{ r.quarantined_count }}</td>
            <td>{{ r.skipped_count }}</td>
            <td>{{ r.cursor_before }}→{{ r.cursor_after }}</td>
            <td>{{ r.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
