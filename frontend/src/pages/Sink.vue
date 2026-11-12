<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await getJSON('/api/sink') })
</script>
<template>
  <div class="page">
    <h1>Sink</h1>
    <p class="muted">已成功应用的实体当前态（delete 后行消失）。</p>
    <div class="panel">
      <table>
        <thead>
          <tr><th>流</th><th>entity_key</th><th>last_seq</th><th>last_event_ts</th><th>payload</th><th>updated</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.stream_id }}</td>
            <td>{{ r.entity_key }}</td>
            <td>{{ r.last_seq }}</td>
            <td>{{ r.last_event_ts }}</td>
            <td><pre class="mono">{{ JSON.stringify(r.payload) }}</pre></td>
            <td>{{ r.updated_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
