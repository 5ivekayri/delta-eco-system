"""Device registry and operational activity."""
from alembic import op
import sqlalchemy as sa
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def common():
    return [sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table('devices', *common(),
        sa.Column('device_uid', sa.String(128), unique=True, nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('hostname', sa.String(255), nullable=False),
        sa.Column('os', sa.String(16), nullable=False),
        sa.Column('architecture', sa.String(64), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('agent_version', sa.String(32), nullable=False),
        sa.Column('capabilities', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False))
    op.create_table('activity', *common(),
        sa.Column('event_type', sa.String(64), nullable=False, index=True),
        sa.Column('source', sa.String(64), nullable=False),
        sa.Column('device_id', sa.String(36), nullable=True, index=True),
        sa.Column('workspace_id', sa.String(36), nullable=True),
        sa.Column('service_id', sa.String(128), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=False))


def downgrade():
    op.drop_table('activity')
    op.drop_table('devices')
