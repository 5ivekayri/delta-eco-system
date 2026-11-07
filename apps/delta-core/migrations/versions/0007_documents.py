"""Core-owned documents and immutable DOCX revisions."""
from alembic import op
import sqlalchemy as sa
revision='0007'
down_revision='0006'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('documents',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('owner_id',sa.String(64),nullable=False),sa.Column('name',sa.String(255),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_documents_owner_id','documents',['owner_id'])
    op.create_table('document_versions',sa.Column('document_id',sa.String(36),sa.ForeignKey('documents.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('revision',sa.Integer(),primary_key=True),sa.Column('content',sa.LargeBinary(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    op.drop_table('document_versions');op.drop_index('ix_documents_owner_id',table_name='documents');op.drop_table('documents')
