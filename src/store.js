import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useLearning = defineStore('learning', () => {
  const token = ref(localStorage.getItem('zhixu-token') || '')
  const user = ref(null), nodes = ref([]), rules = ref({}), report = ref(null), recommendations = ref(null)
  const error = ref(''), loading = ref(false)
  async function api(path, options = {}) {
    const response = await fetch('/api' + path, { ...options, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token.value}`, ...options.headers } })
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
  async function refresh() {
    const [k, r, rec] = await Promise.all([api('/knowledge'), api('/report'), api('/recommendations')])
    nodes.value = k.nodes; rules.value = k.rules; report.value = r; recommendations.value = rec
  }
  async function authenticate(username, password, register = false) {
    const data = await api(`/auth/${register ? 'register' : 'login'}`, { method: 'POST', body: JSON.stringify({ username, password }) })
    token.value = data.token; user.value = data.user; localStorage.setItem('zhixu-token', token.value)
    await refresh()
  }
  async function restore() { if (token.value) { user.value = await api('/me'); await refresh() } }
  async function logout() {
    await api('/auth/logout', { method: 'POST' })
    token.value = ''; user.value = null; localStorage.removeItem('zhixu-token')
    nodes.value = []; report.value = null; recommendations.value = null
  }
  function name(id) { return nodes.value.find(n => n.id === id)?.name || id }
  return { token, user, nodes, rules, report, recommendations, error, loading, api, run, refresh, authenticate, restore, logout, name }
})
export const percent = v => v == null ? '未评估' : `${Math.round(v * 100)}%`
export const difficultyName = n => ['', '基础', '中等', '提升'][n]
