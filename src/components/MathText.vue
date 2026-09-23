<script setup>
import { computed } from 'vue'
import katex from 'katex'
const props = defineProps({ text: { type: String, default: '' } })
const parts = computed(() => props.text.split(/(\$[^$]+\$)/g).map(t => ({ text: t, html: t.startsWith('$') && t.endsWith('$') ? katex.renderToString(t.slice(1, -1), { throwOnError: false, trust: false, strict: 'error', maxExpand: 200, maxSize: 20 }) : null })))
</script>
<template><span><template v-for="(part, i) in parts" :key="i"><span v-if="part.html" v-html="part.html"></span><template v-else>{{ part.text }}</template></template></span></template>
