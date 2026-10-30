import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// Account-level endpoints; every other path belongs to the current course (/api/courses/{course}/...).
const isGlobal = path => path.startsWith('/auth/') || path === '/me' || path.startsWith('/courses')

export const useLearning = defineStore('learning', () => {
  const token = ref(localStorage.getItem('zhixu-token') || '')
  const course = ref(localStorage.getItem('zhixu-course') || 'hs-math'), courses = ref([])
  const user = ref(null), nodes = ref([]), rules = ref({}), report = ref(null), recommendations = ref(null)
  const error = ref(''), loading = ref(false)
  const currentCourse = computed(() => courses.value.find(c => c.id === course.value) || null)
  // Platform admins manage every course; otherwise staff rights come from the role inside this course.
  const isStaff = computed(() => user.value?.role === 'admin' || ['teacher', 'ta'].includes(currentCourse.value?.role))
  const goalId = computed(() => recommendations.value?.goal_id || null)
  function apiPath(path) { return isGlobal(path) ? '/api' + path : `/api/courses/${encodeURIComponent(course.value)}${path}` }
  async function api(path, options = {}) {
    const json = !(options.body instanceof FormData)
    const response = await fetch(apiPath(path), { ...options, headers: { ...(json ? { 'Content-Type': 'application/json' } : {}), Authorization: `Bearer ${token.value}`, ...options.headers } })
    const body = await response.json()
    if (!response.ok) {
      if (response.status === 401 && user.value) { token.value = ''; user.value = null; localStorage.removeItem('zhixu-token') }
      const message = Array.isArray(body.detail) ? body.detail.map(d => `${d.loc.join('.')}：${d.msg}`).join('；') : body.detail
      throw new Error(message || '请求失败，请稍后重试')
    }
    return body
  }
  async function run(fn) {
    error.value = ''
    try { return await fn() } catch (e) { error.value = e.message; return null }
  }
  function setCourse(id) { course.value = id; localStorage.setItem('zhixu-course', id) }
  async function loadCourses() {
    courses.value = await api('/courses')
    if (courses.value.length && !currentCourse.value) setCourse(courses.value[0].id)
  }
  async function refresh() {
    nodes.value = []; report.value = null; recommendations.value = null
    if (!currentCourse.value) return
    const [k, r, rec] = await Promise.all([api('/knowledge'), api('/report'), api('/recommendations')])
    nodes.value = k.nodes; rules.value = k.rules; report.value = r; recommendations.value = rec
  }
  async function switchCourse(id) {
    if (id === course.value && nodes.value.length) return
    setCourse(id)
    await refresh()
  }
  async function authenticate(username, password, register = false) {
    const data = await api(`/auth/${register ? 'register' : 'login'}`, { method: 'POST', body: JSON.stringify({ username, password }) })
    token.value = data.token; localStorage.setItem('zhixu-token', token.value)
    await loadCourses()
    await refresh()
    // Set last: pages mount once user is set and read course data (goal, nodes) synchronously.
    user.value = data.user
  }
  async function restore() { if (token.value) { user.value = await api('/me'); await loadCourses(); await refresh() } }
  async function logout() {
    await api('/auth/logout', { method: 'POST' })
    token.value = ''; user.value = null; localStorage.removeItem('zhixu-token')
    courses.value = []; nodes.value = []; report.value = null; recommendations.value = null
  }
  function name(id) { return nodes.value.find(n => n.id === id)?.name || id }
  return { token, course, courses, currentCourse, isStaff, goalId, user, nodes, rules, report, recommendations, error, loading,
           api, apiPath, run, refresh, loadCourses, switchCourse, authenticate, restore, logout, name }
})
export const percent = v => v == null ? '未评估' : `${Math.round(v * 100)}%`
export const difficultyName = n => ['', '基础', '中等', '提升'][n]
