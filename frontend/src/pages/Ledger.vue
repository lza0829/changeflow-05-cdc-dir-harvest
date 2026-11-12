<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await getJSON('/api/ledger') })
</script>
<template>
  <div class="page">
    <h1>变更账本</h1>
    <p class="muted">每次采集 / Apply 写入的事件处置记录（与报告同源）：采集成功先记 collected，Apply 时改写为 applied / skipped_duplicate / quarantine_gap。</p>
    <div class="panel">
      <table>
        <thead>
          <tr><th>ID</th><th>流</th><th>run</th><th>采集任务</th><th>seq</th><th>op</th><th>entity</th><th>disposition</th><th>event_ts</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.stream_id }}</td>
            <td>{{ r.run_id ?? '—' }}</td>
            <td>{{ r.harvest_task_id ? `#${r.harvest_task_id}` : '—' }}</td>
            <td>{{ r.seq }}</td>
            <td>{{ r.op }}</td>
            <td>{{ r.entity_key }}</td>
            <td>
              <span class="tag" :class="r.disposition === 'applied' ? 'ok' : (r.disposition === 'collected' ? 'warn' : 'danger')">{{ r.disposition }}</span>
            </td>
            <td>{{ r.event_ts }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
