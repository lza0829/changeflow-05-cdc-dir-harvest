<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const streams = ref([])
const streamId = ref(1)
const preview = ref(null)
const err = ref('')
async function loadPreview() {
  err.value = ''
  try {
    preview.value = await getJSON(`/api/streams/${streamId.value}/preview`)
  } catch (e) {
    err.value = String(e.message || e)
  }
}
onMounted(async () => {
  streams.value = await getJSON('/api/streams')
  if (streams.value.length) streamId.value = streams.value[0].id
  await loadPreview()
})
</script>
<template>
  <div class="page">
    <h1>样本预览</h1>
    <div class="row-actions panel">
      <label>流
        <select v-model.number="streamId" @change="loadPreview">
          <option v-for="s in streams" :key="s.id" :value="s.id">{{ s.id }} · {{ s.name }}</option>
        </select>
      </label>
      <button @click="loadPreview">刷新</button>
    </div>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel" v-if="preview">
      <p class="muted">共 {{ preview.count }} 条（展示前 50）</p>
      <table>
        <thead><tr><th>seq</th><th>op</th><th>entity_key</th><th>event_ts</th><th>payload</th></tr></thead>
        <tbody>
          <tr v-for="e in preview.events" :key="e.seq">
            <td>{{ e.seq }}</td>
            <td>{{ e.op }}</td>
            <td>{{ e.entity_key }}</td>
            <td>{{ e.event_ts }}</td>
            <td><pre class="mono">{{ JSON.stringify(e.payload) }}</pre></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
