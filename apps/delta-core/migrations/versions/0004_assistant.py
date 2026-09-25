"""Assistant request and tool-result history."""
from alembic import op
import sqlalchemy as sa
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('assistant_history',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('user_message',sa.Text(),nullable=False),sa.Column('assistant_text',sa.Text(),nullable=False),
        sa.Column('tool_calls',sa.JSON(),nullable=False),sa.Column('tool_results',sa.JSON(),nullable=False),sa.Column('device_id',sa.String(36),nullable=True))

def downgrade():
    op.drop_table('assistant_history')
