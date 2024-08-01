"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    with op.batch_alter_table('event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_admin', sa.Boolean(), nullable=True))
        # Add a named constraint for the foreign key
        batch_op.create_foreign_key(
            'fk_event_organization_id', 'organization', ['organization_id'], ['id'])



def downgrade():
    ${downgrades if downgrades else "pass"}
