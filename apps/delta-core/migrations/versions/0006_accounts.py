"""Core-owned accounts and revocable sessions."""
from alembic import op
import sqlalchemy as sa
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None

def upgrade():
    common=lambda:[sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False)]
    op.create_table('account_users',*common(),sa.Column('username',sa.String(64),unique=True,nullable=False),sa.Column('password_hash',sa.String(256),nullable=False),sa.Column('role',sa.String(16),nullable=False),sa.Column('active',sa.Boolean(),nullable=False))
    op.create_table('account_sessions',*common(),sa.Column('digest',sa.String(64),unique=True,nullable=False),sa.Column('user_id',sa.String(36),sa.ForeignKey('account_users.id'),nullable=False),sa.Column('kind',sa.String(16),nullable=False),sa.Column('expires',sa.Float(),nullable=False))
def downgrade():
    op.drop_table('account_sessions');op.drop_table('account_users')
