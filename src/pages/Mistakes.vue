<script setup>
import { ref, onMounted, computed } from 'vue'
import { useLearning } from '../store'
import MathText from '../components/MathText.vue'
const store=useLearning(), items=ref([]), filter=ref('all')
const visible=computed(() => items.value.filter(m => filter.value==='all' || (filter.value==='pending' ? !m.reviewed_at : !!m.reviewed_at)))
onMounted(() => store.run(async () => { items.value=await store.api('/mistakes') }))
</script>
<template><div class="page-heading"><div><p class="eyebrow">让错误成为理解的起点</p><h1>错题本</h1><p>每次答错自动收录，答对复习题后更新复习状态。复习不重复增加有效样本。</p></div><span class="badge">{{ items.filter(m=>!m.reviewed_at).length }} 道待复习</span></div><div class="filter-tabs"><button :class="{active:filter==='all'}" @click="filter='all'">全部错题</button><button :class="{active:filter==='pending'}" @click="filter='pending'">待复习</button><button :class="{active:filter==='done'}" @click="filter='done'">已复习</button></div><article class="mistake-row" v-for="m in visible" :key="m.question.id" data-testid="mistake-row"><div><span class="badge" :class="{'success':m.reviewed_at}">{{ m.status }}</span><span class="muted"> {{ store.name(m.question.knowledge_id) }}</span><h3><MathText :text="m.question.stem"/></h3><p>累计错误 {{ m.error_count }} 次 · 最近答错 {{ new Date(m.last_error_at+'Z').toLocaleString('zh-CN') }}</p></div><RouterLink class="secondary" :to="`/practice?question=${m.question.id}`">针对性复习</RouterLink><RouterLink class="text-button" :to="`/assistant?question=${m.question.id}`">讲解这道题</RouterLink></article><div v-if="!visible.length" class="empty"><span>✓</span><h2>这里暂时没有错题</h2><p>完成练习后，答错的题目会自动出现在这里。</p><RouterLink class="primary" to="/practice">开始练习</RouterLink></div></template>
