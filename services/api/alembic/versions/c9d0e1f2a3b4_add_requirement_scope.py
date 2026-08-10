"""add requirement applicability scope and proposal hierarchy

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "requirement_register",
        sa.Column(
            "scope",
            sa.String(32),
            nullable=False,
            server_default="execution_constraint",
        ),
    )
    op.add_column(
        "requirement_register",
        sa.Column(
            "proposal_path_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "requirement_register",
        sa.Column(
            "acceptance_criteria_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE requirement_register
        SET scope = CASE
          WHEN origin = 'audit' THEN
            CASE WHEN kind = 'evaluation' THEN 'evaluation_rule'
                 WHEN kind IN ('format','prohibition','cross_ref')
                 THEN 'proposal_format' ELSE 'proposal_content' END
          WHEN lower(normalized_text) ~
            '(ценово предложение|предлаганата цена|обосновка по чл[.]? *72|провеждане на жребий|решение за класиране)'
            THEN 'qualification_admin'
          WHEN lower(normalized_text) ~
            '(комплексна оценка|оценка на оферт|оценяване на оферт|класиране на оферт|офертите се класират|методика за оценка|показател за оценка|точки по показател|отстранява от участие|предложението се оценява)'
            AND lower(normalized_text) ~
            '(техническ(ото|о) предложен|предложение за изпълнение|оферт|участие)'
            THEN 'evaluation_rule'
          WHEN lower(normalized_text) ~
            '(техническ(ото|о) предложен|предложение за изпълнение|участникът (трябва|следва) да (представи|опише|предложи|разработи|включи)|програма за организация|линеен график|линейният график|офертата .*съдържа|в програмата|в предложението)'
            THEN CASE WHEN kind IN ('format','prohibition','cross_ref')
                      THEN 'proposal_format' ELSE 'proposal_content' END
          WHEN lower(normalized_text) ~
            '(техническият проект|техническия проект|технически проект трябва|проектната документация|проектът трябва да съдържа|проектна част|обяснителна записка|чертежите към проекта)'
            THEN 'technical_deliverable'
          WHEN lower(normalized_text) ~
            '(еедоп|технически и професионални способности|критерий за подбор|участникът трябва да притежава|изисквания към участника)'
            THEN 'qualification_admin'
          WHEN lower(normalized_text) ~
            '(при сключване на договор|избраният изпълнител|гаранционен срок|договорът|подизпълнител)'
            THEN 'contract_obligation'
          ELSE 'execution_constraint'
        END
        """
    )
    op.drop_constraint(
        "ck_requirement_register_origin", "requirement_register", type_="check"
    )
    op.create_check_constraint(
        "ck_requirement_register_origin",
        "requirement_register",
        "origin IN ('map','audit','proposal_audit','manual')",
    )
    op.create_check_constraint(
        "ck_requirement_register_scope",
        "requirement_register",
        "scope IN ('proposal_content','proposal_format','evaluation_rule',"
        "'execution_constraint','technical_deliverable','qualification_admin',"
        "'contract_obligation')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE requirement_register SET origin = 'audit' "
        "WHERE origin = 'proposal_audit'"
    )
    op.drop_constraint(
        "ck_requirement_register_scope", "requirement_register", type_="check"
    )
    op.drop_constraint(
        "ck_requirement_register_origin", "requirement_register", type_="check"
    )
    op.create_check_constraint(
        "ck_requirement_register_origin",
        "requirement_register",
        "origin IN ('map','audit','manual')",
    )
    op.drop_column("requirement_register", "acceptance_criteria_json")
    op.drop_column("requirement_register", "proposal_path_json")
    op.drop_column("requirement_register", "scope")
