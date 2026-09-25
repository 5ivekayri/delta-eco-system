"""Workspaces and device bindings."""
from alembic import op
import sqlalchemy as sa
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None

def common():
    return [sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False)]

def upgrade():
    op.create_table('workspaces',*common(),sa.Column('name',sa.String(200),unique=True,nullable=False),sa.Column('description',sa.Text(),nullable=False))
    op.create_table('workspace_bindings',*common(),
        sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id',ondelete='CASCADE'),nullable=False),
        sa.Column('device_id',sa.String(36),sa.ForeignKey('devices.id',ondelete='CASCADE'),nullable=False),
        sa.Column('local_path',sa.Text(),nullable=False),sa.Column('apps',sa.JSON(),nullable=False),sa.Column('urls',sa.JSON(),nullable=False),
        sa.UniqueConstraint('workspace_id','device_id'))

def downgrade():
    op.drop_table('workspace_bindings');op.drop_table('workspaces')
