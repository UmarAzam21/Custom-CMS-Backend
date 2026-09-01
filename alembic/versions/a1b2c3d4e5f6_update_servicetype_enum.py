"""Update servicetype enum with new values

Revision ID: a1b2c3d4e5f6
Revises: f12a3e4b7d29
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9f16e3a08b0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Old enum values
old_values = ('web_development', 'seo', 'graphic_design', 'digital_marketing', 'app_development', 'content_writing', 'other')

# New enum values
new_values = (
    'business_ntn',
    'simple_ntn_registration',
    'business_registration',
    'company_registration',
    'filer_registration',
    'gst_registration',
    'tax_return_filing',
    'fbr_notices',
    'wealth_statement',
    'dts_registration',
    'imp_exp_license_psw',
    'trade_mark_registration',
    'pec_registration',
    'chamber_membership',
    'pseb',
    'dnfbp',
    'other',
)


def upgrade() -> None:
    """Upgrade schema."""
    # Create new enum type
    new_enum = postgresql.ENUM(*new_values, name='servicetype_new')
    new_enum.create(op.get_bind(), checkfirst=False)
    
    # Update old values to 'other' (which exists in both old and new enums)
    op.execute("UPDATE messages SET services = NULL WHERE services NOT IN ('other')")
    op.execute("UPDATE leads SET service_type = 'other' WHERE service_type IN ('web_development', 'seo', 'graphic_design', 'digital_marketing', 'app_development', 'content_writing')")
    
    # Alter columns to use new enum
    op.execute("ALTER TABLE messages ALTER COLUMN services TYPE servicetype_new USING services::text::servicetype_new")
    op.execute("ALTER TABLE leads ALTER COLUMN service_type TYPE servicetype_new USING service_type::text::servicetype_new")
    
    # Drop old enum and rename new one
    op.execute("DROP TYPE servicetype")
    op.execute("ALTER TYPE servicetype_new RENAME TO servicetype")


def downgrade() -> None:
    """Downgrade schema."""
    # Create old enum type
    old_enum = postgresql.ENUM(*old_values, name='servicetype_old')
    old_enum.create(op.get_bind(), checkfirst=False)
    
    # Alter columns back to old enum
    # Note: This will fail if there are values that don't exist in the old enum
    try:
        op.execute("ALTER TABLE messages ALTER COLUMN services TYPE servicetype_old USING services::text::servicetype_old")
        op.execute("ALTER TABLE leads ALTER COLUMN service_type TYPE servicetype_old USING service_type::text::servicetype_old")
    except:
        # If conversion fails, use VARCHAR as fallback
        op.alter_column('messages', 'services', type_=sa.VARCHAR(255))
        op.alter_column('leads', 'service_type', type_=sa.VARCHAR(255))
    
    # Drop new enum and rename old one
    op.execute("DROP TYPE servicetype")
    op.execute("ALTER TYPE servicetype_old RENAME TO servicetype")
