<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await getJSON('/api/cursors') })
</script>
<template>
  <div class="page">
    <h1>游标</h1>
    <p class="muted">流级 apply_cursor 与已应用 seq 集合对账。</p>
    <div class="panel">
      <table>
        <thead>
          <tr><th>流</th><th>名称</th><th>apply_cursor</th><th>applied_seq_count</th><th>max_applied_seq</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.stream_id">
            <td>{{ r.stream_id }}</td>
            <td>{{ r.name }}</td>
            <td>{{ r.apply_cursor }}</td>
            <td>{{ r.applied_seq_count }}</td>
            <td>{{ r.max_applied_seq }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
