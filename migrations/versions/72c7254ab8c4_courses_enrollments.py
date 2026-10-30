"""courses_enrollments

Introduce courses as the isolation unit. Every pre-existing row is moved into the default
course 'hs-math'; users.goal_id moves to enrollments.goal_id. Knowledge ids are unchanged.
"""
import json
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = '72c7254ab8c4'
down_revision = '41b7a28e6461'
branch_labels = None
depends_on = None

DEFAULT_COURSE = 'hs-math'
# Kept in sync with backend.seed.DEFAULT_COURSE_ROW (migrations must not import application code).
DEFAULT_SETTINGS = {'open_enrollment': True, 'assistant': {'persona': '高中数学智能学习助手', 'formula': 'katex',
                    'scope_note': '本库目前仅覆盖高中数学函数与导数路径'}}
COURSE_TABLES = ('knowledge', 'kb_documents', 'practice_sessions', 'ai_conversations')

def _c():
    # Typed binds so offline (--sql) generation can render literals, e.g. for MySQL review.
    return sa.bindparam('c', DEFAULT_COURSE, type_=sa.String(40))

def _sqlite():
    return op.get_bind().dialect.name == 'sqlite'

def _goal_fk_name():
    # SQLite foreign keys are unnamed (batch mode rebuilds the table); MySQL names it automatically.
    if _sqlite():
        return None
    if op.get_context().as_sql:
        return 'users_ibfk_1'
    for fk in sa.inspect(op.get_bind()).get_foreign_keys('users'):
        if fk['constrained_columns'] == ['goal_id']:
            return fk['name']

def upgrade():
    if _sqlite():
        # Rebuilding parent tables (knowledge) in batch mode must not trip FK enforcement mid-copy.
        op.execute('PRAGMA foreign_keys=OFF')
    op.create_table('courses',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('subject', sa.String(length=30), nullable=False),
    sa.Column('level', sa.String(length=20), nullable=False),
    sa.Column('language', sa.String(length=10), nullable=False),
    sa.Column('settings', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('knowledge_drafts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('course_id', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('source_documents', sa.JSON(), nullable=False),
    sa.Column('model_meta', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('reviewed_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_drafts_course_id'), 'knowledge_drafts', ['course_id'], unique=False)
    op.create_table('enrollments',
    sa.Column('course_id', sa.String(length=40), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('goal_id', sa.String(length=50), nullable=True),
    sa.Column('joined_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.ForeignKeyConstraint(['goal_id'], ['knowledge.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('course_id', 'user_id')
    )
    op.create_index(op.f('ix_enrollments_user_id'), 'enrollments', ['user_id'], unique=False)

    # 1) Default course, 2) nullable course_id + backfill, 3) enrollments from users, 4) tighten constraints.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # JSON is passed as text: offline (--sql) mode cannot render JSON literals; both SQLite and MySQL accept it.
    op.execute(sa.text("INSERT INTO courses (id, name, subject, level, language, settings, status, created_by, created_at) "
                       "VALUES (:c, :name, 'math', 'high', 'zh', :settings, 'active', NULL, :now)")
               .bindparams(_c(), sa.bindparam('name', '高中数学（函数与导数）', type_=sa.String(100)),
                           sa.bindparam('settings', json.dumps(DEFAULT_SETTINGS, ensure_ascii=False), type_=sa.Text()),
                           sa.bindparam('now', now, type_=sa.DateTime())))
    for table in COURSE_TABLES:
        op.add_column(table, sa.Column('course_id', sa.String(length=40), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET course_id = :c").bindparams(_c()))
    op.execute(sa.text("INSERT INTO enrollments (course_id, user_id, role, goal_id, joined_at) "
                       "SELECT :c, id, CASE WHEN role = 'admin' THEN 'teacher' ELSE 'student' END, goal_id, :now FROM users")
               .bindparams(_c(), sa.bindparam('now', now, type_=sa.DateTime())))
    for table in COURSE_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column('course_id', existing_type=sa.String(length=40), nullable=False)
            if table == 'kb_documents':
                batch.alter_column('knowledge_id', existing_type=sa.String(length=50), nullable=True)
            batch.create_index(f'ix_{table}_course_id', ['course_id'], unique=False)
            batch.create_foreign_key(f'fk_{table}_course_id', 'courses', ['course_id'], ['id'])
    with op.batch_alter_table('users') as batch:
        name = _goal_fk_name()
        if name:
            batch.drop_constraint(name, type_='foreignkey')
        batch.drop_column('goal_id')
    if _sqlite():
        op.execute('PRAGMA foreign_keys=ON')

def downgrade():
    bind = op.get_bind()
    if not op.get_context().as_sql:
        others = bind.execute(sa.text('SELECT COUNT(*) FROM courses WHERE id != :c').bindparams(c=DEFAULT_COURSE)).scalar()
        if others:
            raise RuntimeError('库中存在默认课程以外的课程，降级会丢失课程归属，已拒绝。')
    if _sqlite():
        op.execute('PRAGMA foreign_keys=OFF')
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('goal_id', sa.String(length=50), nullable=True))
        batch.create_foreign_key('fk_users_goal_id', 'knowledge', ['goal_id'], ['id'])
    op.execute(sa.text('UPDATE users SET goal_id = (SELECT goal_id FROM enrollments e WHERE e.user_id = users.id AND e.course_id = :c)')
               .bindparams(_c()))
    for table in reversed(COURSE_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f'fk_{table}_course_id', type_='foreignkey')
            batch.drop_index(f'ix_{table}_course_id')
            if table == 'kb_documents':
                batch.alter_column('knowledge_id', existing_type=sa.String(length=50), nullable=False)
            batch.drop_column('course_id')
    op.drop_index(op.f('ix_enrollments_user_id'), table_name='enrollments')
    op.drop_table('enrollments')
    op.drop_index(op.f('ix_knowledge_drafts_course_id'), table_name='knowledge_drafts')
    op.drop_table('knowledge_drafts')
    op.drop_table('courses')
    if _sqlite():
        op.execute('PRAGMA foreign_keys=ON')
