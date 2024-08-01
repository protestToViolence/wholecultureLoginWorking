"""Add organization_id to Event

Revision ID: 4a29befe6701
Revises: 
Create Date: 2024-07-01 16:22:20.827376

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import Integer, MetaData

# revision identifiers, used by Alembic.
revision = '4a29befe6701'
down_revision = None
branch_labels = None
depends_on = None

def column_exists(engine, table_name, column_name):
    inspector = sa.inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def upgrade():
    bind = op.get_bind()
    if not column_exists(bind, 'event', 'organization_id'):
        # Create a temporary table for existing events without organization_id
        event_table = table('event', column('organization_id', Integer))

        with op.batch_alter_table('event', schema=None) as batch_op:
            batch_op.add_column(sa.Column('organization_id', sa.Integer(), nullable=True))
        
        # Set default value for organization_id for existing records
        op.execute(
            event_table.update().values({'organization_id': 1})
        )

        with op.batch_alter_table('event', schema=None) as batch_op:
            batch_op.alter_column('organization_id', existing_type=sa.Integer(), nullable=False)
            batch_op.create_foreign_key('fk_event_organization', 'organization', ['organization_id'], ['id'])

    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_organization_name'), ['name'], unique=False)

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('username',
               existing_type=sa.VARCHAR(length=80),
               type_=sa.String(length=150),
               existing_nullable=False)
        batch_op.alter_column('password_hash',
               existing_type=sa.VARCHAR(length=128),
               type_=sa.String(length=200),
               existing_nullable=False)
        batch_op.create_index(batch_op.f('ix_user_username'), ['username'], unique=True)

def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_username'))
        batch_op.alter_column('password_hash',
               existing_type=sa.String(length=200),
               type_=sa.VARCHAR(length=128),
               existing_nullable=False)
        batch_op.alter_column('username',
               existing_type=sa.String(length=150),
               type_=sa.VARCHAR(length=80),
               existing_nullable=False)

    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_organization_name'))

    with op.batch_alter_table('event', schema=None) as batch_op:
        batch_op.drop_constraint('fk_event_organization', type_='foreignkey')
        batch_op.drop_column('organization_id')
