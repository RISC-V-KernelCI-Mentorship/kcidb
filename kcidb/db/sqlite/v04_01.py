"""Kernel CI report database - SQLite schema v4.1"""

import logging
import kcidb.io as io
from kcidb.misc import merge_dicts
from kcidb.db.sqlite.schema import \
    Constraint, BoolColumn, IntegerColumn, TextColumn, \
    JSONColumn, Table
from .v04_00 import Schema as PreviousSchema

# Module's logger
LOGGER = logging.getLogger(__name__)


class Schema(PreviousSchema):
    """SQLite database schema v4.1"""

    # The schema's version.
    version = (4, 1)
    # The I/O schema the database schema supports
    io = io.schema.V4_2

    # A map of table names and Table constructor arguments
    # For use by descendants
    TABLES_ARGS = dict(
        **PreviousSchema.TABLES_ARGS,
        issues=dict(
            columns={
                "id": TextColumn(constraint=Constraint.NOT_NULL),
                "version": IntegerColumn(constraint=Constraint.NOT_NULL),
                "origin": TextColumn(constraint=Constraint.NOT_NULL),
                "report_url": TextColumn(),
                "report_subject": TextColumn(),
                "culprit.code": BoolColumn(),
                "culprit.tool": BoolColumn(),
                "culprit.harness": BoolColumn(),
                "build_valid": BoolColumn(),
                "test_status": TextColumn(),
                "comment": TextColumn(),
                "misc": JSONColumn()
            },
            primary_key=["id", "version"]
        ),
        incidents=dict(
            columns={
                "id": TextColumn(constraint=Constraint.PRIMARY_KEY),
                "origin": TextColumn(constraint=Constraint.NOT_NULL),
                "issue_id": TextColumn(constraint=Constraint.NOT_NULL),
                "issue_version":
                    IntegerColumn(constraint=Constraint.NOT_NULL),
                "build_id": TextColumn(),
                "test_id": TextColumn(),
                "present": BoolColumn(),
                "comment": TextColumn(),
                "misc": JSONColumn(),
            }
        ),
    )

    # A map of table names and schemas
    TABLES = {
        name: Table(**args) for name, args in TABLES_ARGS.items()
    }

    # Queries and their columns for each type of raw object-oriented data.
    # Both should have columns in the same order.
    OO_QUERIES = merge_dicts(
        PreviousSchema.OO_QUERIES,
        issue=merge_dicts(
            PreviousSchema.OO_QUERIES["issue"],
            statement="SELECT\n"
                      "    id,\n"
                      "    origin\n"
                      "FROM issues\n"
                      "GROUP BY id",
        ),
        issue_version=merge_dicts(
            PreviousSchema.OO_QUERIES["issue_version"],
            statement="SELECT\n"
                      "    id,\n"
                      "    version AS version_num,\n"
                      "    origin,\n"
                      "    report_url,\n"
                      "    report_subject,\n"
                      "    \"culprit.code\" AS culprit_code,\n"
                      "    \"culprit.tool\" AS culprit_tool,\n"
                      "    \"culprit.harness\" AS culprit_harness,\n"
                      "    comment,\n"
                      "    misc\n"
                      "FROM issues",
        ),
        incident=merge_dicts(
            PreviousSchema.OO_QUERIES["incident"],
            statement="SELECT\n"
                      "    id,\n"
                      "    origin,\n"
                      "    issue_id,\n"
                      "    issue_version AS issue_version_num,\n"
                      "    build_id,\n"
                      "    test_id,\n"
                      "    present,\n"
                      "    comment,\n"
                      "    misc\n"
                      "FROM incidents",
        ),
    )

    @classmethod
    def _inherit(cls, conn):
        """
        Inerit the database data from the previous schema version (if any).

        Args:
            conn:   Connection to the database to inherit. The database must
                    comply with the previous version of the schema.
        """
        assert isinstance(conn, cls.Connection)
        with conn:
            cursor = conn.cursor()
            try:
                for table_name, table_schema in cls.TABLES.items():
                    if table_name not in PreviousSchema.TABLES:
                        try:
                            cursor.execute(
                                table_schema.format_create(table_name)
                            )
                        except Exception as exc:
                            raise Exception(
                                f"Failed creating table {table_name!r}"
                            ) from exc
            finally:
                cursor.close()
