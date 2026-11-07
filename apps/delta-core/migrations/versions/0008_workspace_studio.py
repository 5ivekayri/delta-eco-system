"""Workspace storage and work type."""
from alembic import op
import sqlalchemy as sa
revision='0008'
down_revision='0007'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('workspaces',sa.Column('storage_mode',sa.String(16),nullable=False,server_default='cloud'))
    op.add_column('workspaces',sa.Column('work_type',sa.String(16),nullable=False,server_default='general'))
    op.add_column('workspaces',sa.Column('storage_device_id',sa.String(36),nullable=True))

def downgrade():
    op.drop_column('workspaces','storage_device_id')
    op.drop_column('workspaces','work_type')
    op.drop_column('workspaces','storage_mode')
