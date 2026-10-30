"""initial_web_training

Revision ID: 0001
Revises:
Create Date: 2026-10-30 06:51:50.529888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 固定第一版结构；后续模型变更请创建新的迁移，不要修改本版本。
    op.create_table('courses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('video_file', sa.String(length=100), nullable=False),
    sa.Column('duration', sa.Float(), nullable=False),
    sa.Column('required_percent', sa.Integer(), nullable=False),
    sa.Column('pass_score', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('exam_minutes', sa.Integer(), nullable=False),
    sa.Column('published', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('password_hash', sa.String(length=256), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.Float(), nullable=False),
    sa.Column('deadline', sa.Float(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('pass_score', sa.Integer(), nullable=False),
    sa.Column('submitted_at', sa.Float(), nullable=True),
    sa.Column('answers', sa.JSON(), nullable=True),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('passed', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('login_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('expires', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_table('progress',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('segments', sa.JSON(), nullable=False),
    sa.Column('watched', sa.Float(), nullable=False),
    sa.Column('position', sa.Float(), nullable=False),
    sa.Column('watch_token', sa.String(length=64), nullable=False),
    sa.Column('last_seen', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'course_id')
    )
    op.create_table('questions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('options', sa.JSON(), nullable=False),
    sa.Column('answer', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )



def downgrade() -> None:
    """Downgrade schema."""
    # 按外键依赖的逆序删除；降级会丢失数据，执行前必须备份。
    op.drop_table('questions')
    op.drop_table('progress')
    op.drop_table('login_sessions')
    op.drop_table('attempts')
    op.drop_table('users')
    op.drop_table('courses')
