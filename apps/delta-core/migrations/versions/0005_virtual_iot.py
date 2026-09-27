"""Persistent singleton virtual IoT state."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table('virtual_iot_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('desk_light', sa.Boolean(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=False),
        sa.Column('brightness', sa.Integer(), nullable=False),
        sa.Column('motion', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('id = 1', name='iot_singleton'),
        sa.CheckConstraint('brightness >= 0 AND brightness <= 100', name='iot_brightness_range'))
    from datetime import datetime, timezone
    op.bulk_insert(table, [{'id':1,'desk_light':False,'temperature':23.0,'brightness':30,'motion':True,
                           'updated_at':datetime.now(timezone.utc)}])


def downgrade():
    op.drop_table('virtual_iot_state')
