"""Provider boundary: only a genuine provider response may produce real tool calls."""
import asyncio
import json
import logging
import time
from typing import Protocol
import httpx

logger=logging.getLogger(__name__)

class ModelError(Exception):
    def __init__(self, code, message): self.code=code; super().__init__(message)

class Provider(Protocol):
    async def complete(self,messages,tools,trace_id,max_tokens): ...

class DeepSeekProvider:
    def __init__(self,config,transport=None):self.config=config;self.transport=transport;self.client=None;self.loop=None
    async def aclose(self):
        if self.client:await self.client.aclose();self.client=None
    async def complete(self,messages,tools,trace_id,max_tokens):
        c=self.config
        if not c.key: raise ModelError('not_configured','模型尚未配置，请管理员在服务端设置 API Key。')
        payload=dict(model=c.model,messages=messages,temperature=0,max_tokens=max_tokens,stream=False,thinking={'type':'disabled'},response_format={'type':'json_object'})
        if tools:payload.update(tools=tools,tool_choice='auto')
        started=time.monotonic()
        for attempt in range(c.retries+1):
            try:
                # Agent rounds and retries in one request reuse the connection; a client never crosses event loops.
                loop=asyncio.get_running_loop()
                if not self.client or self.loop is not loop:self.client=httpx.AsyncClient(timeout=c.timeout,transport=self.transport);self.loop=loop
                response=await self.client.post(c.base_url+'/chat/completions',headers={'Authorization':'Bearer '+c.key,'X-Request-ID':trace_id},json=payload)
                if response.status_code>=400:
                    code='auth' if response.status_code in (401,403) else ('rate_limit' if response.status_code==429 else ('upstream' if response.status_code>=500 else 'invalid_request'))
                    raise ModelError(code,{'auth':'模型服务认证失败。','rate_limit':'模型请求限流，请稍后重试。','upstream':'模型服务暂不可用。','invalid_request':'模型服务拒绝请求，请管理员检查模型配置。'}[code])
                body=response.json(); choice=body['choices'][0]
                if choice.get('finish_reason') not in ('stop','tool_calls'):raise ModelError('incomplete','模型回答未完整生成，请缩短问题后重试。')
                message=choice['message']
                if not isinstance(message,dict):raise ModelError('invalid_response','模型返回格式不正确。')
                usage=body.get('usage')
                if not isinstance(usage,dict) or any(type(usage.get(k)) is not int or usage[k]<0 for k in ('prompt_tokens','completion_tokens')):usage=None
                return {'message':message,'usage':usage,'elapsed_ms':round((time.monotonic()-started)*1000),'provider_attempts':attempt+1}
            except httpx.TimeoutException:
                error=ModelError('timeout','模型请求超时，请稍后重试。')
            except httpx.RequestError:
                error=ModelError('network','无法连接模型服务。')
            except (KeyError,ValueError,IndexError,TypeError,AttributeError):
                error=ModelError('invalid_response','模型返回格式不正确。')
            except ModelError as exc:error=exc
            if attempt>=c.retries or error.code not in ('timeout','network','rate_limit','upstream'):
                error.provider_attempts=attempt+1
                raise error
            logger.warning('model retry trace=%s attempt=%s code=%s',trace_id,attempt+1,error.code)
            await asyncio.sleep(.3*(attempt+1))

class TestMockProvider:
    """Explicit deterministic fixture, NOT an LLM, never selected by real-mode errors."""
    async def complete(self,messages,tools,trace_id,max_tokens):
        has_results=any(m['role']=='tool' for m in messages)
        if tools and not has_results:
            calls=[{'id':f'mock-{i}','type':'function','function':{'name':name,'arguments':json.dumps(args)}} for i,(name,args) in enumerate([
                ('get_learning_profile',{}),('get_wrong_questions',{'limit':5}),('get_mastery',{'knowledge_id':'derivative_rules'}),
                ('get_prerequisites',{'knowledge_id':'extrema'}),('recommend_practice',{}),('search_knowledge',{'query':'导数计算 幂函数求导','knowledge_id':'derivative_rules'})])]
            return {'message':{'role':'assistant','content':None,'tool_calls':calls},'usage':None,'elapsed_ms':0,'provider_attempts':0}
        evidence=[];submitted=None
        for m in messages:
            if m['role']=='user' and m['content'].startswith('资料包：'):
                pack=json.loads(m['content'][4:]);evidence+=pack.get('evidence',[]);submitted=pack.get('submitted_question')
            if m['role']=='tool':
                data=json.loads(m['content']);evidence+=data.get('evidence',[])
        ids=[e['chunk_id'] for e in evidence[:2]]
        plan=None
        for m in messages:
            if m['role']=='tool':
                data=json.loads(m['content'])
                if data.get('draft_template'):plan=data['draft_template']
        text='**测试 Mock 回答，不是真实模型输出。**\n\n'+(evidence[0]['content'] if evidence else '当前没有足够证据，请补充知识点或题目背景。')
        if submitted:text+='\n\n服务端已提交题目：你选择了 '+str(submitted['selected'])+'（从0开始），原题答案为 '+str(submitted['answer'])+'。\n\n'+submitted['explanation']
        return {'message':{'role':'assistant','content':json.dumps({'answer':text,'citations':ids,'plan':plan},ensure_ascii=False)},'usage':None,'elapsed_ms':0,'provider_attempts':0}

def make_provider(config):
    if config.mode=='mock':
        if not config.allow_mock:raise ModelError('mock_disabled','Mock 仅限明确开启的测试环境。')
        return TestMockProvider()
    if config.mode!='real':raise ModelError('invalid_config','未知模型模式。')
    return DeepSeekProvider(config)
