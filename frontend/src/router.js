import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './pages/Dashboard.vue'
import Streams from './pages/Streams.vue'
import Preview from './pages/Preview.vue'
import Harvest from './pages/Harvest.vue'
import Apply from './pages/Apply.vue'
import Ledger from './pages/Ledger.vue'
import Quarantine from './pages/Quarantine.vue'
import Sink from './pages/Sink.vue'
import Cursors from './pages/Cursors.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/streams', component: Streams },
    { path: '/preview', component: Preview },
    { path: '/apply', component: Apply },
    { path: '/harvest', component: Harvest },
    { path: '/ledger', component: Ledger },
    { path: '/quarantine', component: Quarantine },
    { path: '/sink', component: Sink },
    { path: '/cursors', component: Cursors },
  ],
})
