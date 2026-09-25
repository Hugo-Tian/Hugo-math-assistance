<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLearning } from './store'
const store = useLearning(), route = useRoute(), router = useRouter()
const username = ref('demo_foundation'), password = ref('DemoMath2026!'), registering = ref(false), busy = ref(false), booting = ref(true)
const links = [['/', '⌂', '学习首页'], ['/knowledge', '⌘', '知识树'], ['/levels', '⚑', '学习闯关'], ['/practice', '✎', '练习中心'], ['/search', '⌕', '题库搜索'], ['/mistakes', '▤', '错题本'], ['/report', '▥', '学习报告'], ['/assistant', '✧', '学习助手']]
onMounted(async () => { await store.run(() => store.restore()); booting.value = false })
async function login() { busy.value = true; await store.run(() => store.authenticate(username.value, password.value, registering.value)); busy.value = false }
async function logout() { await store.run(() => store.logout()); router.push('/') }
</script>
<template>
  <div v-if="booting" class="boot">正在连接你的学习空间…</div>
  <div v-else-if="!store.user" class="login-layout">
    <section class="login-intro"><div class="brandmark">知序<span>高中数学智能学习助手</span></div><div><p class="eyebrow">高中数学 · 学习从理解开始</p><h1>每一步，<br>都有自己的顺序。</h1><p>从一次作答出发，发现薄弱点，补齐先修知识，<br>让下一步学习有据可循。</p><div class="path-preview"><span>函数基础</span><i>→</i><span>导数计算</span><i>→</i><span>函数极值</span></div></div><small>作品集演示版本 / 规则学习闭环 + 有据可查的 AI 辅导</small></section>
    <section class="login-form"><form @submit.prevent="login"><p class="eyebrow">欢迎来到知序</p><h2>{{ registering ? '创建学习账号' : '进入学习空间' }}</h2><p>保留每次尝试，看见每一步变化。</p><label>用户名<input v-model="username" autocomplete="username" required minlength="3" maxlength="60" placeholder="字母、数字、下划线"/></label><label>密码<input v-model="password" type="password" :autocomplete="registering ? 'new-password' : 'current-password'" required minlength="8" maxlength="128"/></label><p v-if="store.error" role="alert" class="error">{{ store.error }}</p><button class="primary wide" :disabled="busy">{{ busy ? '正在验证账号…' : registering ? '注册并开始学习' : '登录' }}</button><button type="button" class="text-button wide" @click="registering = !registering">{{ registering ? '已有账号？返回登录' : '创建新账号，体验冷启动' }}</button><div class="demo-note"><strong>体验不同的学习起点</strong><p>以下账号含明确标注的模拟历史，密码均为 DemoMath2026!</p><button type="button" @click="username = 'demo_foundation'; password = 'DemoMath2026!'">基础巩固 · demo_foundation</button><button type="button" @click="username = 'demo_advanced'; password = 'DemoMath2026!'">导数进阶 · demo_advanced</button><button type="button" @click="username = 'demo_admin'; password = 'DemoMath2026!'">内容管理 · demo_admin</button></div></form></section>
  </div>
  <div v-else class="shell">
    <aside class="sidebar"><RouterLink class="brandmark" to="/">知序<span>高中数学智能学习助手</span></RouterLink><div class="subject">高中数学 <span>第一版</span></div><nav aria-label="主导航"><RouterLink v-for="[path, icon, text] in links" :key="path" :to="path"><span aria-hidden="true">{{ icon }}</span>{{ text }}</RouterLink><RouterLink v-if="store.user.role === 'admin'" to="/admin"><span aria-hidden="true">⚙</span>内容管理</RouterLink><RouterLink v-if="store.user.role === 'admin'" to="/knowledge-admin"><span aria-hidden="true">▧</span>知识库管理</RouterLink></nav><div class="sidebar-bottom"><div class="avatar">{{ store.user.username.slice(0,1).toUpperCase() }}</div><strong>{{ store.user.username }}</strong><small>{{ store.user.is_demo ? '演示账号 · 含模拟历史' : '个人学习账号' }}</small><button class="text-button" @click="logout">退出登录</button></div></aside>
    <div class="workspace"><header class="topbar"><span>我的学习空间 <span class="muted">/ {{ route.meta.title }}</span></span><span class="top-status"><i></i>学习记录已连接</span><button class="text-button mobile-logout" @click="logout">退出登录</button></header><main><div v-if="store.error" class="error global-error" role="alert">{{ store.error }}<button @click="store.error = ''" aria-label="关闭错误提示">×</button></div><RouterView :key="route.path"/></main><footer>知序 · 高中数学演示题库 <span>AI 辅导需配置模型 · 拍照搜题与视频未开放</span></footer></div>
  </div>
</template>
