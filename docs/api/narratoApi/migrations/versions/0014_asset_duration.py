"""记录媒体探测后的真实时长，供项目费用快照使用。"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_asset_duration"
down_revision: str | None = "0013_project_deletion_worker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("duration_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("assets", "duration_seconds")
