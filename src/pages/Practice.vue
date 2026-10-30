<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLearning, percent, difficultyName } from '../store'
import MathText from '../components/MathText.vue'
const store=useLearning(), route=useRoute(), router=useRouter()
const mode=ref(route.query.knowledge ? 'custom' : 'adaptive'), knowledge=ref(route.query.knowledge || store.nodes[0]?.id || ''), difficulty=ref(1), count=ref(5)
const session=ref(null), result=ref(null), selected=ref(null), busy=ref(false), retryKey=ref('')
const question=computed(() => session.value?.question)
async function start() { busy.value=true; await store.run(async () => {
  session.value=await store.api('/sessions', {method:'POST',body:JSON.stringify({mode:mode.value, knowledge_id:mode.value === 'custom' ? knowledge.value : null, difficulty:mode.value === 'custom' ? Number(difficulty.value) : null,count:Number(count.value)})})
  result.value=null; selected.value=null; retryKey.value=''; await router.replace({path:'/practice',query:{session:session.value.id}})
}); busy.value=false }
async function submit() { if (selected.value == null || busy.value) return; busy.value=true; await store.run(async () => {
  if (!retryKey.value) retryKey.value=crypto.randomUUID()
  result.value=await store.api(`/sessions/${session.value.id}/answers`,{method:'POST',body:JSON.stringify({question_id:question.value.id,selected:selected.value,idempotency_key:retryKey.value})})
  await store.refresh()
}); busy.value=false }
async function next() { busy.value=true; await store.run(async () => {
  session.value=await store.api(`/sessions/${session.value.id}`); result.value=null; selected.value=null; retryKey.value=''
}); busy.value=false }
async function reset() { session.value=null; result.value=null; await router.replace('/practice') }
onMounted(() => store.run(async () => {
  if(route.query.session) session.value=await store.api(`/sessions/${route.query.session}`)
  if(route.query.question) {
    session.value=await store.api('/sessions',{method:'POST',body:JSON.stringify({mode:'review',question_id:Number(route.query.question),count:1})})
    await router.replace({path:'/practice',query:{session:session.value.id}})
  }
}))
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">每次作答，都是新的学习线索</p><h1>练习中心</h1><p>专注一道题，积累真正有效的理解。</p></div><button v-if="session" class="secondary" @click="reset">选择另一组练习</button></div>
  <div v-if="!session" class="practice-setup"><div class="mode-tabs"><button :class="{active:mode==='adaptive'}" @click="mode='adaptive'"><strong>自适应练习</strong><span>每次作答后，重新推荐下一题</span></button><button :class="{active:mode==='custom'}" @click="mode='custom'"><strong>自定义练习</strong><span>按知识点、难度和题量练习</span></button></div><section class="panel"><template v-if="mode==='adaptive'"><h2>从你的当前状态出发</h2><p>{{ store.recommendations?.recommendations[0]?.reason }}</p><div class="callout">先修不足时，系统会选择具体的先修知识点。基础诊断积累足够样本后，再逐步调整难度。</div></template><div v-else class="form-grid"><label>知识点<select v-model="knowledge" aria-label="知识点"><option v-for="n in store.nodes" :key="n.id" :value="n.id">{{ n.name }}</option></select></label><label>难度<select v-model="difficulty" aria-label="难度"><option :value="1">基础</option><option :value="2">中等</option><option :value="3">提升</option></select></label></div><label class="count-field">题量<select v-model="count" aria-label="题量"><option :value="1">1 道</option><option :value="5">5 道</option><option :value="10">10 道</option><option :value="20">20 道</option></select></label><p class="muted">题量不足时将明确提示实际数量；不会重复填充题目。</p><button class="primary" @click="start" :disabled="busy">{{ busy ? '正在准备…' : '开始练习' }}</button></section><div class="rule-note">掌握度 =（正确次数 + 1）/（有效次数 + 2）。最近最多 20 条有效记录；同题每天最多一次计入掌握度，已看过答案的题目仅作复习记录。</div></div>
  <div v-else-if="question" class="question-layout"><section class="question-panel"><div class="question-toolbar"><span>第 {{ session.answered+1 }} 题 / {{ session.mode==='adaptive' ? session.requested_count : session.actual_count }} 题</span><span class="badge">{{ store.name(question.knowledge_id) }} · {{ difficultyName(question.difficulty) }}</span></div><div class="progress-track"><i :style="{width:`${session.answered/session.requested_count*100}%`}"></i></div><p v-if="session.notice" class="callout">{{ session.notice }}</p><h2 class="question-stem"><MathText :text="question.stem"/></h2><div class="answer-options"><button v-for="(option,i) in question.options" :key="i" :data-testid="`option-${i}`" :disabled="!!result || busy" :class="{chosen:selected===i, correct:result && result.answer===i, incorrect:result && selected===i && !result.correct}" @click="selected=i; retryKey=''" :aria-pressed="selected===i"><span>{{ 'ABCD'[i] }}</span><MathText :text="option"/></button></div><p class="source">{{ question.source }}</p><button v-if="!result" class="primary" :disabled="selected==null || busy" @click="submit">{{ busy ? '保存中…' : '提交答案' }}</button><div v-else class="answer-feedback" :class="{wrong:!result.correct}" data-testid="answer-feedback"><RouterLink class="text-button" :to="`/assistant?question=${result.question_id}`">讲解这道题</RouterLink><h3>{{ result.correct ? '回答正确' : '还差一步，看看解题思路' }}</h3><p>正确答案：{{ 'ABCD'[result.answer] }}</p><p><MathText :text="result.explanation"/></p><div class="feedback-mastery">当前掌握度 <strong>{{ percent(result.mastery) }}</strong> · {{ result.samples }} 条有效样本</div><p>{{ result.effective ? '本次已计入掌握度。' : result.exclusion_reason }}</p><button class="primary" @click="next" :disabled="busy">{{ session.answered+1 >= (session.mode==='adaptive'?session.requested_count:session.actual_count) ? '查看练习总结' : '下一题' }}</button></div></section><aside class="practice-aside"><h3>把每一步留给思考</h3><p>选择答案后提交。判题、掌握度和下一步推荐由服务器统一计算。</p><template v-if="result?.recommendation"><hr><h3>新的下一步建议</h3><strong>{{ result.recommendation.name }}</strong><p>{{ result.recommendation.reason }}</p></template><RouterLink to="/mistakes">查看错题本 →</RouterLink></aside></div>
  <section v-else class="session-summary panel"><span class="summary-symbol">✓</span><h2>这一组，已完成</h2><p v-if="session.notice">{{ session.notice }}</p><div class="metrics"><div><span>完成题目</span><strong>{{ session.answered }}</strong></div><div><span>答对题目</span><strong>{{ session.correct }}</strong></div><div><span>有效样本</span><strong>{{ session.effective }}</strong></div></div><div class="summary-results"><p v-for="r in session.results" :key="r.attempt_id">{{ store.name(r.knowledge_id) }} · {{ r.correct ? '正确' : '错误' }} · {{ r.effective ? '有效计分' : '复习记录' }}</p></div><div class="actions"><RouterLink class="primary" to="/report">查看学习报告</RouterLink><RouterLink class="secondary" to="/">查看下一步推荐</RouterLink></div></section>
</template>
