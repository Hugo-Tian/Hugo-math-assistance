import os
from dataclasses import dataclass

@dataclass
class Settings:
    mode: str = 'real'
    key: str = ''
    base_url: str = 'https://api.deepseek.com'
    model: str = 'deepseek-flash'
    timeout: float = 25
    retries: int = 1
    max_rounds: int = 4
    max_tools: int = 8
    token_budget: int = 64000
    output_tokens: int = 1600
    context_chars: int = 14000
    request_seconds: int = 100
    allow_mock: bool = False
    embedding_model: str = 'BAAI/bge-small-zh-v1.5'
    embedding_cache: str = 'storage/models'
    index_dir: str = 'storage/index'
    retrieval_mode: str = 'vector'
    top_k: int = 5
    vector_threshold: float = .65
    keyword_threshold: float = .08
    rag_chars: int = 5000

    @classmethod
    def from_env(cls):
        return cls(mode=os.getenv('LLM_MODE','real'),key=os.getenv('LLM_API_KEY') or os.getenv('DEEPSEEK_API_KEY',''),
            base_url=os.getenv('LLM_BASE_URL','https://api.deepseek.com').rstrip('/'),model=os.getenv('LLM_MODEL','deepseek-flash'),
            timeout=float(os.getenv('LLM_TIMEOUT_SECONDS','25')),retries=min(2,max(0,int(os.getenv('LLM_MAX_RETRIES','1')))),
            max_rounds=min(6,max(1,int(os.getenv('LLM_MAX_ROUNDS','4')))),max_tools=min(12,max(1,int(os.getenv('LLM_MAX_TOOL_CALLS','8')))),
            token_budget=int(os.getenv('LLM_TOKEN_BUDGET','64000')),output_tokens=int(os.getenv('LLM_MAX_OUTPUT_TOKENS','1600')),
            context_chars=int(os.getenv('LLM_CONTEXT_CHARS','14000')),request_seconds=int(os.getenv('LLM_REQUEST_SECONDS','100')),
            allow_mock=os.getenv('ALLOW_TEST_MOCK','false').lower()=='true',embedding_model=os.getenv('EMBEDDING_MODEL','BAAI/bge-small-zh-v1.5'),
            embedding_cache=os.getenv('EMBEDDING_CACHE','storage/models'),index_dir=os.getenv('RAG_INDEX_DIR','storage/index'),
            retrieval_mode=os.getenv('RAG_MODE','vector'),top_k=min(10,max(1,int(os.getenv('RAG_TOP_K','5')))),
            vector_threshold=float(os.getenv('RAG_VECTOR_THRESHOLD','.65')),keyword_threshold=float(os.getenv('RAG_KEYWORD_THRESHOLD','.08')),
            rag_chars=int(os.getenv('RAG_CONTEXT_CHARS','5000')))

def settings(): return Settings.from_env()
