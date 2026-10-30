import hashlib
import io
import json
import math
import os
import re
import uuid
from collections import Counter
from functools import lru_cache
from pathlib import Path
from sqlalchemy import select, delete
from pypdf import PdfReader
from .models import Document, Chunk
from ..models import Knowledge, Attempt, Question, PracticeSession
from .provider import ModelError
from ..service import session_expired
from ..courses import DEFAULT_COURSE, rules_for
from ..models import Course

MAX_FILE_BYTES=5*1024*1024

def assessment_open(db,user_id,course_id=None):
    """Unfinished, unexpired practices of this course (or of every course when course_id is None)."""
    attempts=list(db.scalars(select(Attempt).where(Attempt.user_id==user_id)))
    answered=set((a.session_id,a.question_id) for a in attempts);last={}
    for a in attempts:last[a.session_id]=max(last.get(a.session_id,a.created_at),a.created_at)
    query=select(PracticeSession).where(PracticeSession.user_id==user_id,PracticeSession.ended.is_(False))
    if course_id:query=query.where(PracticeSession.course_id==course_id)
    timeouts={}
    def timeout(cid):
        if cid not in timeouts:timeouts[cid]=rules_for(db.get(Course,cid)).assessment_timeout_minutes
        return timeouts[cid]
    # Abandoned practices expire, so they no longer block tutoring indefinitely.
    return [s.id for s in db.scalars(query)
            if any((s.id,q) not in answered for q in s.question_ids) and not session_expired(s,last.get(s.id),minutes=timeout(s.course_id))]

def permitted_question(db,user_id,qid):
    return bool(db.scalar(select(Attempt.id).where(Attempt.user_id==user_id,Attempt.question_id==qid).limit(1)))

def split_text(text,title,max_chars=1100):
    """Heading/paragraph/math-block aware; oversized atomic derivations are rejected, not cut."""
    lines=text.replace('\r\n','\n').splitlines();sections=[];heading=title;parts=[];block=[];math_block=False;fence=False
    def flush_block():
        if block:
            value='\n'.join(block).strip();block.clear()
            if len(value)>max_chars*3:raise ValueError('单个段落或公式过长，请按推导步骤分段后导入')
            if value:parts.append(value)
    def flush_section():
        flush_block();buffer=[];size=0
        for p in parts:
            if buffer and size+len(p)>max_chars:sections.append((heading,'\n\n'.join(buffer)));buffer=[];size=0
            buffer.append(p);size+=len(p)+2
        if buffer:sections.append((heading,'\n\n'.join(buffer)))
        parts.clear()
    for line in lines:
        if line.strip().startswith('```'):fence=not fence
        if line.count('$$')%2:math_block=not math_block
        if re.match(r'^#{1,6}\s+',line) and not math_block and not fence:
            flush_section();heading=re.sub(r'^#+\s*','',line).strip()[:200]
        elif not line.strip() and not math_block and not fence:flush_block()
        else:block.append(line)
    if math_block or fence:raise ValueError('公式块或代码块未闭合')
    flush_section()
    return sections

def import_document(db,filename,data,kid,source,question_id=None,title=None,document_id=None,course_id=None):
    if len(data)>MAX_FILE_BYTES:raise ValueError('文件不能超过 5 MB')
    extension=Path(filename).suffix.lower()
    if extension not in ('.md','.txt','.pdf'):raise ValueError('仅支持 Markdown、TXT 和文本型 PDF')
    knowledge=db.get(Knowledge,kid) if kid else None
    if kid and not knowledge:raise ValueError('知识点不存在')
    # Course-wide documents carry no knowledge point; otherwise the course follows the knowledge point.
    course_id=course_id or (knowledge.course_id if knowledge else None)
    if not course_id or not db.get(Course,course_id):raise ValueError('请指定资料所属课程')
    if knowledge and knowledge.course_id!=course_id:raise ValueError('知识点不属于本课程')
    question=db.get(Question,question_id) if question_id else None
    if question_id and (not question or db.get(Knowledge,question.knowledge_id).course_id!=course_id):raise ValueError('受限题目不存在')
    checksum=hashlib.sha256(data).hexdigest()
    if db.scalar(select(Document.id).where(Document.checksum==checksum)):raise ValueError('此文件已经导入，请勿重复上传')
    doc=Document(id=document_id or str(uuid.uuid4()),title=title or Path(filename).stem,filename=Path(filename).name[:200],checksum=checksum,
        source=source,course_id=course_id,knowledge_id=kid,scope='question' if question_id else 'public',question_id=question_id,status='processing')
    db.add(doc);db.flush()
    try:
        if extension=='.pdf':
            reader=PdfReader(io.BytesIO(data))
            if reader.is_encrypted:raise ValueError('不支持加密 PDF')
            if len(reader.pages)>100:raise ValueError('PDF 最多 100 页')
            pages=[(i+1,page.extract_text() or '') for i,page in enumerate(reader.pages)]
            if any(len(text.strip())<15 for _,text in pages):raise ValueError('PDF 存在无可提取文本的页面，可能是扫描件，需要 OCR；本版未开放 OCR')
        else:pages=[(None,data.decode('utf-8-sig'))]
        if sum(len(t) for _,t in pages)>250000:raise ValueError('文本超过 25 万字符')
        chunks=[]
        for page,text in pages:
            for heading,content in split_text(text,doc.title):
                chunks.append(Chunk(id=f'{doc.id}-{len(chunks):03d}',document_id=doc.id,title=heading,chapter=knowledge.chapter,page=page,content=content,position=len(chunks)))
        if not chunks:raise ValueError('文档没有可处理的文本')
        db.add_all(chunks);doc.status='parsed'
    except Exception as exc:
        doc.status='failed';doc.error=str(exc)[:250] if isinstance(exc,(ValueError,UnicodeError)) else '文件解析失败，请检查格式'
    db.flush()
    return doc

def allowed_chunks(db,user_id,knowledge_id=None,guard=True,course_id=DEFAULT_COURSE):
    if guard and assessment_open(db,user_id,course_id):return []
    rows=db.execute(select(Chunk,Document).join(Document,Document.id==Chunk.document_id).where(Document.course_id==course_id,Document.active.is_(True),
        Document.status.in_(['parsed','indexed'])).execution_options(populate_existing=True)).all()
    allowed_questions=set(db.scalars(select(Attempt.question_id).where(Attempt.user_id==user_id)))
    return [(c,d) for c,d in rows if (not knowledge_id or d.knowledge_id==knowledge_id) and (d.scope=='public' or d.question_id in allowed_questions)]

def chunk_payload(c,d,score=None):
    return dict(chunk_id=c.id,document_id=d.id,title=c.title,chapter=c.chapter,page=c.page,knowledge_id=d.knowledge_id,
        content=c.content,version=d.version,source=d.source,score=score,scope=d.scope)

def tokens(text):
    text=re.sub(r'\s+','',text.lower());words=re.findall(r'[a-z0-9_]+',text)
    for run in re.findall(r'[\u4e00-\u9fff]+',text):words.extend(run[i:i+2] for i in range(len(run)-1))
    return Counter(words)

def lexical_score(query,text):
    a,b=tokens(query),tokens(text)
    return sum(min(v,b[k]) for k,v in a.items())/max(1,sum(a.values()))

@lru_cache(maxsize=2)
def embedding_model(name,cache):
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=name,cache_dir=cache,threads=2,local_files_only=os.getenv('EMBEDDING_ALLOW_DOWNLOAD','false').lower()!='true')

@lru_cache(maxsize=2)
def embedding_fingerprint(name,cache):
    model=embedding_model(name,cache)
    directory=Path(model.model._model_dir)
    digest=hashlib.sha256()
    for path in sorted(directory.rglob('*.onnx')):
        with path.open('rb') as file:
            for block in iter(lambda:file.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def embed(texts,config,query=False):
    import numpy as np
    try:
        model=embedding_model(config.embedding_model,config.embedding_cache)
        vectors=list(model.query_embed(texts) if query else model.passage_embed(texts))
        matrix=np.asarray(vectors,dtype='float32')
        matrix/=np.maximum(np.linalg.norm(matrix,axis=1,keepdims=True),1e-9)
        return matrix
    except Exception:raise ModelError('embedding_unavailable','中文向量模型不可用；请管理员完成模型下载和索引初始化。') from None

def rebuild_index(db,config):
    import faiss
    from filelock import FileLock
    directory=Path(config.index_dir);directory.mkdir(parents=True,exist_ok=True)
    with FileLock(str(directory/'build.lock'),timeout=3):
        rows=db.execute(select(Chunk,Document).join(Document).where(Document.active.is_(True),Document.status.in_(['parsed','indexed'])).order_by(Chunk.id)).all()
        if not rows:raise ValueError('没有可建立索引的资料')
        vectors=embed([c.title+'\n'+c.content for c,d in rows],config)
        index=faiss.IndexFlatIP(vectors.shape[1]);index.add(vectors)
        version=uuid.uuid4().hex
        faiss.write_index(index,str(directory/f'{version}.faiss'))
        manifest=dict(version=version,model=config.embedding_model,model_fingerprint=embedding_fingerprint(config.embedding_model,config.embedding_cache),dimension=vectors.shape[1],ids=[c.id for c,d in rows],
            hashes={c.id:hashlib.sha256(c.content.encode()).hexdigest() for c,d in rows},file=f'{version}.faiss')
        pending=directory/f'{version}.json';pending.write_text(json.dumps(manifest),encoding='utf-8')
        os.replace(pending,directory/'manifest.json')
        for _,d in rows:d.status='indexed';d.error=None
        db.commit()
        return dict(version=version,chunks=len(rows),dimension=vectors.shape[1],model=config.embedding_model)

@lru_cache(maxsize=2)
def load_index(path):
    # Index files are immutable per version (a rebuild writes a new uuid file), so the path is a safe cache key.
    import faiss
    return faiss.read_index(path)

def vector_scores(rows,query,config):
    directory=Path(config.index_dir)
    try:manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):raise ModelError('index_missing','知识库尚未建立向量索引，请管理员初始化。')
    if manifest['model']!=config.embedding_model:raise ModelError('index_incompatible','Embedding 模型已变更，需要重建索引。')
    vector=embed([query],config,query=True)
    if manifest.get('model_fingerprint')!=embedding_fingerprint(config.embedding_model,config.embedding_cache):raise ModelError('index_incompatible','Embedding 权重版本与索引不同，请重建索引。')
    index=load_index(str(directory/manifest['file']))
    if vector.shape[1]!=manifest['dimension'] or index.d!=manifest['dimension']:raise ModelError('index_incompatible','Embedding 维度与索引不一致。')
    # SQL authorization first. Unpermitted results are never turned into contexts.
    permitted={c.id:(c,d) for c,d in rows}
    distances,indices=index.search(vector,len(manifest['ids']))
    scores=[]
    for score,i in zip(distances[0],indices[0]):
        cid=manifest['ids'][i] if i>=0 else None
        if cid in permitted:
            c,d=permitted[cid]
            if manifest['hashes'][cid]==hashlib.sha256(c.content.encode()).hexdigest():scores.append((float(score),c,d))
    return scores,manifest['version']

def hybrid_scores(rows,query,config,rrf_k=60):
    """RRF over vector and keyword ranks. A chunk is admitted when the vector score clears the normal threshold,
    or when both signals are moderately strong (keyword >= hybrid_keyword, vector >= hybrid_vector_floor)."""
    vectors,version=vector_scores(rows,query,config)
    keywords={c.id:lexical_score(query,c.title+' '+c.content) for c,d in rows}
    vector_rank={c.id:i for i,(s,c,d) in enumerate(sorted(vectors,key=lambda x:(-x[0],x[1].id)))}
    keyword_rank={cid:i for i,cid in enumerate(sorted(keywords,key=lambda k:(-keywords[k],k)))}
    scores=[]
    for s,c,d in vectors:
        if s>=config.vector_threshold or (keywords[c.id]>=config.hybrid_keyword and s>=config.hybrid_vector_floor):
            scores.append((1/(rrf_k+vector_rank[c.id]+1)+1/(rrf_k+keyword_rank[c.id]+1),c,d))
    return scores,version

def retrieve(db,user_id,query,config,knowledge_id=None,mode=None,top_k=None,course_id=DEFAULT_COURSE):
    rows=allowed_chunks(db,user_id,knowledge_id,course_id=course_id)
    if not rows:return {'evidence':[],'mode':mode or config.retrieval_mode,'index_version':None}
    mode=mode or config.retrieval_mode;top_k=top_k or config.top_k
    if mode=='keyword':
        scores=[(lexical_score(query,c.title+' '+c.content),c,d) for c,d in rows];threshold=config.keyword_threshold;version='keyword-v1'
    elif mode=='vector':
        scores,version=vector_scores(rows,query,config);threshold=config.vector_threshold
    elif mode=='hybrid':
        # Admission is decided inside hybrid_scores; RRF values are only for ordering.
        scores,version=hybrid_scores(rows,query,config);threshold=0;version='hybrid-'+version
    else:raise ValueError('未知检索模式')
    scores.sort(key=lambda x:(-x[0],x[1].id));evidence=[];length=0
    for score,c,d in scores:
        if score<threshold or len(evidence)>=top_k:break
        if length+len(c.content)>config.rag_chars:continue
        evidence.append(chunk_payload(c,d,round(score,6)));length+=len(c.content)
    return dict(evidence=evidence,mode=mode,index_version=version,threshold=threshold)
