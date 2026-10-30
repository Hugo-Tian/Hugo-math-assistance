<script setup>
import { computed, ref } from 'vue'
import { useLearning, percent } from '../store'
import { useRouter } from 'vue-router'
const store = useLearning(), router = useRouter()
const recs = computed(() => store.recommendations?.recommendations || [])
const goal = ref(store.goalId || '')
const passed = computed(() => store.nodes.filter(n => n.passed_at).length)
async function saveGoal() { await store.run(async () => { await store.api('/me/goal', { method: 'PUT', body: JSON.stringify({ knowledge_id: goal.value || null }) }); await store.refresh() }) }
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">今天，从适合你的地方开始</p><h1>让学习有迹可循</h1><p>理解当前状态，再选择下一步。</p></div><span class="badge">{{ store.user.is_demo ? '模拟历史演示' : '个人学习记录' }}</span></div>
  <div class="dashboard-grid"><section class="next-task" v-if="recs.length"><div class="section-label">下一步建议 <span>自适应推荐</span></div><h2 data-testid="recommendation-name">{{ recs[0].name }}</h2><p class="recommendation-reason">{{ recs[0].reason }}</p><div class="task-path"><span>发现薄弱点</span><i>→</i><span class="active">针对性练习</span><i>→</i><span>更新学习报告</span></div><button class="primary" @click="router.push('/practice?mode=adaptive')">开始自适应练习 <span>→</span></button><details><summary>为什么推荐这项任务？</summary><p>综合分 {{ recs[0].score.toFixed(3) }} · {{ recs[0].version }}</p><div class="contributions"><span>薄弱贡献 {{ recs[0].contributions.weakness.toFixed(3) }}</span><span>复习贡献 {{ recs[0].contributions.urgency.toFixed(3) }}</span><span>目标贡献 {{ recs[0].contributions.goal.toFixed(3) }}</span></div><p>{{ store.recommendations.default_rule }}</p></details></section><section class="goal-panel"><p class="eyebrow">我的学习目标</p><h2>走向更完整的理解</h2><label>目标知识点<select v-model="goal" @change="saveGoal"><option value="">未设置 · 按基础顺序诊断</option><option v-for="n in store.nodes" :value="n.id" :key="n.id">{{ n.name }}</option></select></label><p>推荐会优先检查先修缺口，逐步走向目标。</p><div class="goal-count"><strong>{{ passed }}<small> / {{ store.nodes.length }}</small></strong><span>历史已通过知识点</span></div><RouterLink to="/knowledge">查看完整知识路径 →</RouterLink></section></div>
  <div class="metrics"><div><span>累计答题</span><strong>{{ store.report?.total || 0 }}<small> 次</small></strong></div><div><span>有效样本</span><strong>{{ store.report?.effective || 0 }}<small> 条</small></strong></div><div><span>全部尝试正确率</span><strong>{{ percent(store.report?.accuracy) }}</strong></div><div><span>模拟历史</span><strong>{{ store.report?.simulated || 0 }}<small> 条</small></strong></div></div>
  <section class="section"><div class="section-heading"><h2>后续学习建议</h2><RouterLink to="/practice">自定义练习 →</RouterLink></div><div class="recommendation-list"><article v-for="(rec,i) in recs.slice(1,4)" :key="rec.knowledge_id"><span class="order">{{ String(i+2).padStart(2,'0') }}</span><div><h3>{{ rec.name }}</h3><p>{{ rec.reason }}</p></div><span class="badge">{{ rec.cold_start ? '基础诊断' : '巩固复习' }}</span></article></div></section>
  <section class="comparison"><h3>同一目标，两种顺序</h3><p>固定章节顺序：<strong>{{ store.name(store.recommendations?.fixed_order_next) }}</strong> <span>→</span> 当前自适应建议：<strong>{{ recs[0]?.name || '暂无建议' }}</strong></p><small>仅展示选题行为差异；不代表已验证学习效果提升。</small></section>
</template>
