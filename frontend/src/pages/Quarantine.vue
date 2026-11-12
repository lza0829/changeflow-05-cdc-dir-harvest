<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await getJSON('/api/quarantine') })
</script>
<template>
  <div class="page">
    <h1>隔离区</h1>
    <p class="muted">缺口、毒丸等未能提交的事件落此（默认缺口停）。</p>
    <div class="panel">
      <table>
        <thead>
          <tr><th>ID</th><th>流</th><th>run</th><th>seq</th><th>entity</th><th>reason</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.stream_id }}</td>
            <td>{{ r.run_id }}</td>
            <td>{{ r.seq }}</td>
            <td>{{ r.entity_key }}</td>
            <td>{{ r.reason }}</td>
            <td>{{ r.created_at }}</td>
          </tr>
          <tr v-if="!rows.length"><td colspan="7" class="muted">暂无隔离记录</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
