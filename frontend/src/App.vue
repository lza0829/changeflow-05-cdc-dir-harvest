<template>
  <div class="layout-pipe">
    <aside class="pipe-rail">
      <div class="brand">变流 Changeflow</div>
      <router-link to="/">总览</router-link>
      <router-link to="/streams">变更流</router-link>
      <router-link to="/preview">样本预览</router-link>
      <router-link to="/apply">应用台</router-link>
      <router-link to="/ledger">变更账本</router-link>
      <router-link to="/quarantine">隔离区</router-link>
      <router-link to="/sink">Sink</router-link>
      <router-link to="/cursors">游标</router-link>
    </aside>
    <main><router-view /></main>
  </div>
</template>
