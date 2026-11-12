<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api'
const stats = ref(null)
const err = ref('')
onMounted(async () => {
  try {
    stats.value = await getJSON('/api/dashboard')
  } catch (e) {
    err.value = String(e.message || e)
  }
})
</script>
<template>
  <div class="page">
    <header>
      <h1>变流总览</h1>
      <p class="muted">变更事件入账 → 序/缺口裁决 → 幂等应用到 Sink → 游标对账</p>
    </header>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="tiles" v-if="stats">
      <div class="tile"><div class="hero-num">{{ stats.stream_count }}</div><div class="muted">变更流</div></div>
      <div class="tile"><div class="hero-num">{{ stats.enabled_streams }}</div><div class="muted">启用</div></div>
      <div class="tile"><div class="hero-num">{{ stats.sink_count }}</div><div class="muted">Sink</div></div>
      <div class="tile"><div class="hero-num">{{ stats.quarantine_count }}</div><div class="muted">隔离</div></div>
      <div class="tile"><div class="hero-num">{{ stats.run_count }}</div><div class="muted">Apply Runs</div></div>
    </div>
    <router-link to="/apply">去应用台跑一趟 →</router-link>
  </div>
</template>
