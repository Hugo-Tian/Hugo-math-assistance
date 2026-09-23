import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './pages/Dashboard.vue'
import Knowledge from './pages/Knowledge.vue'
import KnowledgeMap from './pages/KnowledgeMap.vue'
import Assistant from './pages/Assistant.vue'
import KnowledgeAdmin from './pages/KnowledgeAdmin.vue'
import Practice from './pages/Practice.vue'
import Search from './pages/Search.vue'
import Mistakes from './pages/Mistakes.vue'
import Report from './pages/Report.vue'
import Admin from './pages/Admin.vue'
import './style.css'
import 'katex/dist/katex.min.css'

const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/', component: Dashboard, meta: { title: '学习首页' } },
  { path: '/knowledge', component: KnowledgeMap, meta: { title: '知识树' } },
  { path: '/levels', component: Knowledge, meta: { title: '学习闯关' } },
  { path: '/practice', component: Practice, meta: { title: '练习中心' } },
  { path: '/search', component: Search, meta: { title: '题库搜索' } },
  { path: '/mistakes', component: Mistakes, meta: { title: '错题本' } },
  { path: '/report', component: Report, meta: { title: '学习报告' } },
  { path: '/admin', component: Admin, meta: { title: '内容管理' } },
  { path: '/assistant', component: Assistant, meta: { title: '学习助手' } },
  { path: '/knowledge-admin', component: KnowledgeAdmin, meta: { title: '知识库管理' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
] })
createApp(App).use(createPinia()).use(router).mount('#app')
