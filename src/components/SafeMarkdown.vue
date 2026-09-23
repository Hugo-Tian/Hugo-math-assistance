<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import katex from 'katex'
const props=defineProps({text:{type:String,default:''}})
const rendered=computed(()=>{
  const formulas=[]
  const source=props.text.replace(/\$\$([\s\S]+?)\$\$|\$([^\n$]+)\$/g,(_,block,inline)=>{
    const id=formulas.length
    formulas.push(katex.renderToString(block||inline,{displayMode:!!block,throwOnError:false,trust:false,maxExpand:200,maxSize:20}))
    return `ZXMATHPLACEHOLDER${id}ENDZX`
  })
  // Raw HTML is text; model links/images have no navigation or network side effects.
  const renderer=new marked.Renderer()
  renderer.html=({text})=>text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
  renderer.link=({text})=>text
  renderer.image=({text})=>text || ''
  let html=marked.parse(source,{renderer,breaks:true,gfm:true})
  html=html.replace(/ZXMATHPLACEHOLDER(\d+)ENDZX/g,(_,id)=>formulas[Number(id)] || '')
  return DOMPurify.sanitize(html,{FORBID_TAGS:['script','iframe','img','a','form','input','button'],FORBID_ATTR:['onerror','onclick','onload']})
})
</script>
<template><div class="safe-markdown" v-html="rendered"></div></template>
<style scoped>.safe-markdown{overflow-wrap:anywhere;line-height:1.9}.safe-markdown :deep(p){color:inherit}.safe-markdown :deep(pre){white-space:pre-wrap;background:#f6f4fb;padding:14px}.safe-markdown :deep(table){display:block;overflow:auto}.safe-markdown :deep(.katex-display){overflow-x:auto;overflow-y:hidden}</style>
