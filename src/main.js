import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { useLearning } from './store'
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
import Teacher from './pages/Teacher.vue'
import Drafts from './pages/Drafts.vue'
import './style.css'
import 'katex/dist/katex.min.css'

const pinia = createPinia()
// Every page lives under /c/:course. Paths written without a course (links, redirects, old bookmarks)
// are rewritten to the current course by the guard below, so pages can keep using short paths like '/practice'.
const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/c/:course', children: [
    { path: '', component: Dashboard, meta: { title: '学习首页' } },
    { path: 'knowledge', component: KnowledgeMap, meta: { title: '知识树' } },
    { path: 'levels', component: Knowledge, meta: { title: '学习闯关' } },
    { path: 'practice', component: Practice, meta: { title: '练习中心' } },
    { path: 'search', component: Search, meta: { title: '题库搜索' } },
    { path: 'mistakes', component: Mistakes, meta: { title: '错题本' } },
    { path: 'report', component: Report, meta: { title: '学习报告' } },
    { path: 'admin', component: Admin, meta: { title: '内容管理' } },
    { path: 'teacher', component: Teacher, meta: { title: '教学看板' } },
    { path: 'drafts', component: Drafts, meta: { title: '知识图谱草稿' } },
    { path: 'assistant', component: Assistant, meta: { title: '学习助手' } },
    { path: 'knowledge-admin', component: KnowledgeAdmin, meta: { title: '知识库管理' } },
    { path: ':pathMatch(.*)*', redirect: to => `/c/${to.params.course}` },
  ] },
  { path: '/:pathMatch(.*)*', component: Dashboard },
] })
router.beforeEach(async to => {
  const store = useLearning(pinia)
  if (!to.path.startsWith('/c/')) return `/c/${store.course}${to.fullPath === '/' ? '' : to.fullPath}`
  const target = to.params.course
  if (target === store.course) return
  // Before login the course list is unknown; App re-validates the course after restoring the session.
  if (store.user && !store.courses.some(c => c.id === target)) return `/c/${store.course}`
  if (store.user) await store.run(() => store.switchCourse(target))
  else store.course = target
})
createApp(App).use(pinia).use(router).mount('#app')
