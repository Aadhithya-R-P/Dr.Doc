"""Record embedding input formatting; don't mislabel older vectors as compatible."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column(
        "embedding_input_version", sa.String(64), nullable=False,
        server_default="legacy-unversioned",
    ))


def downgrade() -> None:
    op.drop_column("documents", "embedding_input_version")
