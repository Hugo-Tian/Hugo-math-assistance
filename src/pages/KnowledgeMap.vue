<script setup>
import { computed, ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLearning, percent } from '../store'

const store = useLearning(), route = useRoute(), router = useRouter()
const selected = ref(route.query.node || ''), viewport = ref(null), scale = ref(1)
const current = computed(() => store.nodes.find(n => n.id === selected.value))
const colors = ['#7462c8', '#528d9a', '#b18548', '#658b6e', '#8e70b0', '#647ac2', '#b7768d']
// Layered DAG layout: column = longest prerequisite chain below the node, so every arrow points rightwards.
// Works for any course's graph; nothing depends on chapter names or node counts.
const COL = 260, ROW = 76, NODE_W = 210, PAD_X = 40, PAD_Y = 50
const layout = computed(() => {
  const byId = Object.fromEntries(store.nodes.map(n => [n.id, n]))
  const chapters = [...new Set(store.nodes.map(n => n.chapter))]
  const depth = {}
  const level = id => {
    if (depth[id] === undefined) {
      depth[id] = 0
      depth[id] = Math.max(0, ...byId[id].prerequisites.filter(p => byId[p]).map(p => level(p) + 1))
    }
    return depth[id]
  }
  store.nodes.forEach(n => level(n.id))
  const columns = []
  for (const n of store.nodes) (columns[depth[n.id]] ||= []).push(n)
  const tallest = Math.max(1, ...columns.map(c => c.length))
  const height = Math.max(420, tallest * ROW + PAD_Y * 2), width = Math.max(760, columns.length * COL + PAD_X * 2 - (COL - NODE_W))
  const nodes = []
  columns.forEach((column, d) => {
    column.sort((x, y) => chapters.indexOf(x.chapter) - chapters.indexOf(y.chapter) || x.position - y.position || x.id.localeCompare(y.id))
    const top = (height - column.length * ROW) / 2 + ROW / 2
    column.forEach((n, i) => nodes.push({ ...n, x: PAD_X + d * COL, y: top + i * ROW, color: colors[chapters.indexOf(n.chapter) % colors.length] }))
  })
  const at = Object.fromEntries(nodes.map(n => [n.id, n]))
  const edges = nodes.flatMap(n => n.prerequisites.filter(p => at[p]).map(p => ({ from: p, to: n.id, path: curve(at[p].x + NODE_W, at[p].y, n.x, n.y) })))
  return { width, height, nodes, edges, columns: columns.length, chapters: chapters.map((name, i) => ({ name, color: colors[i % colors.length] })) }
})
const prerequisites = computed(() => new Set(current.value?.prerequisites || []))
// Highlighted edges: the selected node's direct prerequisites, drawn dashed with an arrow.
const links = computed(() => layout.value.edges.filter(e => e.to === selected.value).map(e => ({ id: e.from, path: e.path })))
function curve(x1,y1,x2,y2) { return `M ${x1} ${y1} C ${(x1+x2)/2} ${y1}, ${(x1+x2)/2} ${y2}, ${x2} ${y2}` }
function choose(id) { selected.value=id; router.replace({path:'/knowledge',query:{node:id}}) }
const fitScale = () => Math.min(1,(viewport.value.clientWidth-30)/layout.value.width)
function fit() { if(viewport.value) {scale.value=fitScale();viewport.value.scrollTo(0,0)} }
// Long prerequisite chains would shrink to unreadable size, so the first view keeps >=60% and centres the selected node.
function initialView() {
  if(!viewport.value) return
  scale.value=Math.max(.6,fitScale())
  const n=layout.value.nodes.find(n=>n.id===selected.value)
  viewport.value.scrollLeft=n ? n.x*scale.value-viewport.value.clientWidth/2+NODE_W*scale.value/2 : 0
}
function zoom(delta) { scale.value=Math.min(1.6,Math.max(.3,scale.value+delta)) }
let observer, drag
function panStart(event) {
  if(event.pointerType!=='mouse' || event.button!==0 || event.target.closest('button')) return
  drag={x:event.clientX,y:event.clientY,left:viewport.value.scrollLeft,top:viewport.value.scrollTop}
  viewport.value.setPointerCapture(event.pointerId)
}
function panMove(event) { if(drag) {viewport.value.scrollLeft=drag.left+drag.x-event.clientX;viewport.value.scrollTop=drag.top+drag.y-event.clientY} }
function panEnd() {drag=null}
onMounted(async () => {await nextTick();initialView();observer=new ResizeObserver(initialView);observer.observe(viewport.value)})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="page-heading"><div><p class="eyebrow">{{ store.currentCourse?.name }} · 知识先修图</p><h1>把知识连成一张地图</h1><p>从左到右按先修顺序排列：最左侧是学习起点，连线由先修知识指向后续知识点。</p></div><RouterLink class="secondary" to="/levels">进入学习闯关</RouterLink></div>
  <section class="mindmap-panel" aria-label="知识思维导图">
    <div class="map-toolbar"><div class="map-key"><span><i class="solid-key"></i>先修关系</span><span><i class="dashed-key"></i>选中节点的直接先修</span><span v-for="c in layout.chapters" :key="c.name" class="chapter-key"><i :style="{background:c.color}"></i>{{ c.name }}</span></div><div class="map-tools"><button @click="zoom(-.1)" aria-label="缩小导图">−</button><output aria-live="polite">{{ Math.round(scale*100) }}%</output><button @click="zoom(.1)" aria-label="放大导图">＋</button><button @click="fit" class="fit-button">适应窗口</button></div></div>
    <div ref="viewport" class="map-viewport" @pointerdown="panStart" @pointermove="panMove" @pointerup="panEnd" @pointercancel="panEnd">
      <div class="map-space" :style="{width:layout.width*scale+'px',height:layout.height*scale+'px'}">
        <div class="map-canvas" :style="{width:layout.width+'px',height:layout.height+'px',transform:`scale(${scale})`}">
          <svg class="map-lines" :width="layout.width" :height="layout.height" aria-hidden="true">
            <defs><marker id="prereq-arrow" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="none" stroke="#534ab7" stroke-width="1.5"/></marker></defs>
            <path v-for="e in layout.edges" :key="e.from+'>'+e.to" :d="e.path" stroke="#c9c2e4" stroke-width="1.6" fill="none" opacity=".8"/>
            <path v-for="link in links" :key="link.id" :d="link.path" stroke="#534ab7" stroke-width="2" stroke-dasharray="6 5" fill="none" marker-end="url(#prereq-arrow)" data-testid="prerequisite-line"/>
          </svg>
          <button v-for="n in layout.nodes" :key="n.id" class="map-node" :class="{selected:selected===n.id,prerequisite:prerequisites.has(n.id),passed:n.status==='已通过',review:n.status==='建议复习'}" :style="{left:n.x+'px',top:n.y-29+'px','--branch-color':n.color}" @click="choose(n.id)" :data-testid="`node-${n.id}`" :aria-pressed="selected===n.id">
            <span class="map-node-title"><i></i><strong>{{ n.name }}</strong><span v-if="n.status==='已通过'" aria-label="已通过">✓</span></span><small>{{ percent(n.mastery) }} · {{ n.samples }} 条样本 <span v-if="n.status==='建议复习'">· 建议复习</span></small>
          </button>
        </div>
      </div>
    </div>
    <div class="map-caption"><span>{{ store.nodes.length }} 个知识点 · {{ layout.columns }} 层先修 · 拖动空白处平移 · 使用 ＋ / − 缩放</span><span v-if="current">已选：{{ current.name }} · {{ current.prerequisites.length }} 个直接先修</span><span v-else>选择一个知识点，探索它的连接</span></div>
  </section>
  <aside class="knowledge-detail map-detail">
    <template v-if="current"><div><p class="eyebrow">{{ current.chapter }} / {{ current.id }}</p><h2>{{ current.name }}</h2><p>{{ current.description }}</p><span class="badge" :class="{success:current.status==='已通过',warning:current.status==='建议复习'}">{{ current.status }}</span></div><div><div class="large-mastery">{{ percent(current.mastery) }}</div><p>{{ current.samples }} 条有效记录 · {{ current.distinct_count }} 道不同题目</p><p v-if="current.passed_at" class="success-text">历史成就：{{ current.passed_at.slice(0,10) }}</p></div><div><h3>必要先修</h3><button v-for="p in current.prerequisites" :key="p" class="prereq-link" @click="choose(p)">{{ store.name(p) }}<span>{{ current.missing_prerequisites.includes(p)?'需要巩固':'已满足' }}</span></button><p v-if="!current.prerequisites.length">学习起点，无先修要求。</p><button class="primary wide" @click="router.push(`/practice?knowledge=${current.id}`)">练习这个知识点</button><RouterLink class="text-button wide" :to="`/assistant?knowledge=${current.id}`">向 AI 提问</RouterLink></div></template>
    <div v-else class="map-empty-detail"><span>⌘</span><div><h2>从一个知识点，看到它的来处与去向</h2><p>点击图中的节点，查看学习状态；虚线箭头由先修知识指向当前知识点。</p></div></div>
  </aside>
</template>

<style scoped>
.mindmap-panel{background:white;border:1px solid var(--border);border-radius:12px;overflow:hidden}.map-toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--border)}.map-key{display:flex;gap:20px;color:var(--muted);font-size:11px}.map-key>span{display:flex;align-items:center;gap:8px}.solid-key,.dashed-key{display:inline-block;width:24px;border-top:2px solid #a095ce}.dashed-key{border-top-style:dashed;border-color:var(--purple)}.chapter-key i{display:inline-block;width:8px;height:8px;border-radius:50%}.map-key{flex-wrap:wrap}.map-tools{display:flex;align-items:center;gap:8px;flex-shrink:0}.map-tools .fit-button{white-space:nowrap}.map-tools button{background:white;border:1px solid var(--border);color:var(--purple);border-radius:5px;min-width:30px;height:30px}.map-tools output{font-size:11px;color:var(--muted);min-width:40px;text-align:center}.map-tools .fit-button{padding:0 10px;margin-left:5px;font-size:11px}.map-viewport{overflow:auto;max-height:690px;min-height:320px;background-color:#fcfbff;background-image:radial-gradient(#dfdbef .7px,transparent .7px);background-size:18px 18px;cursor:grab;overscroll-behavior:contain}.map-viewport:active{cursor:grabbing}.map-space{position:relative;margin:auto;min-width:100%}.map-canvas{position:relative;transform-origin:top left;user-select:none}.map-lines{position:absolute;inset:0;pointer-events:none}.map-node{position:absolute;width:210px;height:58px;background:#fff;border:1px solid #e3dfec;border-left:3px solid var(--branch-color);border-radius:8px;padding:8px 13px;text-align:left;color:#423a59;cursor:pointer;box-shadow:0 2px 5px #29263f04}.map-node:hover{border-color:var(--branch-color);background:#fbfaff}.map-node.selected{background:#eeedfe;border:2px solid #534ab7;box-shadow:0 0 0 4px #534ab710}.map-node.prerequisite{border:2px dashed #8d80c8;background:#f8f6ff}.map-node-title{display:flex;align-items:center;gap:8px}.map-node-title strong{font-size:14px}.map-node-title>span{margin-left:auto;color:#0f6e56}.map-node-title i{width:6px;height:6px;border-radius:50%;background:#c4becf}.map-node.passed .map-node-title i{background:#43a582}.map-node.review .map-node-title i{background:#d19e51}.map-node small{display:block;margin-left:14px;font-size:10px;color:#8e869f;margin-top:2px}.map-caption{border-top:1px solid var(--border);padding:12px 20px;display:flex;justify-content:space-between;gap:10px;color:#9187a4;font-size:10px}.map-detail{position:static;display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:32px;margin-top:20px}.map-detail h2{margin-bottom:8px}.map-detail h3{margin-top:0}.map-detail .large-mastery{margin-top:0}.map-detail .primary{margin-top:18px}.map-empty-detail{grid-column:1/-1;display:flex;align-items:center;gap:22px}.map-empty-detail>span{color:#b2a5d5;font-size:38px}.map-empty-detail h2{font-size:17px}.map-empty-detail p{margin-bottom:0}
@media(max-width:800px){.map-toolbar{flex-wrap:wrap;padding:12px}.map-key{font-size:10px;gap:12px}.map-viewport{min-height:280px}.map-detail{grid-template-columns:1fr;gap:22px}.map-detail>div+div{border-top:1px solid var(--border);padding-top:18px}.map-caption{flex-direction:column;padding:12px}.map-empty-detail{gap:12px}.map-empty-detail h2{font-size:15px}}
</style>
