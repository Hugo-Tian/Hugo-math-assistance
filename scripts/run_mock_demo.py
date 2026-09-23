"""Explicit isolated test server. Never changes the normal application's model mode."""
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT);sys.path.insert(0,str(ROOT))
ROOT.joinpath('tmp').mkdir(exist_ok=True)
os.environ.update(LLM_MODE='mock',ALLOW_TEST_MOCK='true',DATABASE_URL='sqlite:///./tmp/assistant_mock.db')
subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True)
from backend.db import SessionLocal
from backend.seed import seed
from backend.ai.materials import seed_materials
with SessionLocal() as db:seed(db);seed_materials(db)
if __name__=='__main__':
    import uvicorn
    print('TEST MOCK ONLY: isolated database, no real LLM output. http://127.0.0.1:8002')
    uvicorn.run('backend.main:app',host='127.0.0.1',port=8002)
