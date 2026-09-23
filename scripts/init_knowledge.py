import argparse
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import SessionLocal
from backend.ai.materials import seed_materials
from backend.ai.knowledge_base import rebuild_index
from backend.ai.settings import settings

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--index',action='store_true');parser.add_argument('--download-model',action='store_true');args=parser.parse_args()
    if args.download_model:os.environ['EMBEDDING_ALLOW_DOWNLOAD']='true'
    with SessionLocal() as db:
        print('New teaching documents:',seed_materials(db))
        if args.index:print(rebuild_index(db,settings()))
