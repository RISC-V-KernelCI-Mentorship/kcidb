"""Kernel CI report database - SQLite schema v4.0"""

import random
import textwrap
from functools import reduce
from collections import namedtuple
from itertools import chain
import logging
import sqlite3
import dateutil.parser
import kcidb.io as io
import kcidb.orm as orm
from kcidb.misc import LIGHT_ASSERTS
from kcidb.db.schematic import \
    Schema as AbstractSchema, \
    Connection as AbstractConnection
from kcidb.db.sqlite.schema import \
    Constraint, Column, BoolColumn, IntegerColumn, TextColumn, \
    JSONColumn, TimestampColumn, Table


# Module's logger
LOGGER = logging.getLogger(__name__)


class Connection(AbstractConnection):
    """
    Kernel CI SQLite report database connection.
    Exposes SQLite connection interface.
    """

    # Documentation of the connection parameters
    _PARAMS_DOC = textwrap.dedent("""\
        Parameters: <DATABASE>

        <DATABASE>      A path-like object giving the pathname (absolute or
                        relative to the current working directory) of the
                        database file to be opened. Use ":memory:" to create
                        and use an in-memory database.

                        If starts with an exclamation mark ('!'), the
                        in-database data is prioritized explicitly initially,
                        instead of randomly. Double to include one literally.
    """)

    def __init__(self, params):
        """
        Initialize an SQLite connection.

        Args:
            params:         A parameter string describing the database to
                            access. See Connection._PARAMS_DOC for
                            documentation. Cannot be None (must be specified).
        """
        assert params is None or isinstance(params, str)
        if params is None:
            raise Exception("Parameters must be specified\n\n" +
                            self._PARAMS_DOC)

        self.load_prio_db = bool(random.randint(0, 1))
        if params.startswith("!"):
            if not params.startswith("!!"):
                self.load_prio_db = True
            params = params[1:]

        super().__init__(params)

        # Create the connection
        self.conn = sqlite3.connect(params)
        self.conn.set_trace_callback(
            lambda s: LOGGER.debug("Executing:\n%s", s)
        )

    def __getattr__(self, name):
        """Retrieve missing attributes from the SQLite connection object"""
        return getattr(self.conn, name)

    def __enter__(self):
        """Enter the connection runtime context"""
        return self.conn.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        """Leave the connection runtime context"""
        return self.conn.__exit__(exc_type, exc_value, traceback)

    def set_schema_version(self, version):
        """
        Set the schema version of the connected database (or remove it) in a
        separate transaction. Does not modify the data or upgrade its actual
        schema.

        Args:
            version:    A tuple of (major, minor) schema version numbers (both
                        non-negative integers) to set. None to remove the
                        version.
        """
        assert version is None or \
            isinstance(version, tuple) and len(version) == 2 and \
            isinstance(version[0], int) and version[0] >= 0 and \
            isinstance(version[1], int) and version[1] >= 0
        # Oh, but sqlite3 connection is, pylint: disable=not-context-manager
        with self:
            cursor = self.cursor()
            try:
                number = 0 if version is None \
                    else int(version[0] * 1000 + version[1] % 1000)
                cursor.execute(f"PRAGMA user_version = {number}")
            finally:
                cursor.close()

    def get_schema_version(self):
        """
        Retrieve the schema version of the connected database, in a separate
        transaction.

        Returns:
            The major and the minor version numbers of the database schema,
            or None, if not initialized.
        """
        # Oh, but sqlite3 connection is, pylint: disable=not-context-manager
        with self:
            cursor = self.cursor()
            try:
                cursor.execute("PRAGMA user_version")
                number = cursor.fetchone()[0]
                if number:
                    return int(number / 1000), int(number % 1000)
                return None
            finally:
                cursor.close()

    def get_current_time(self):
        """
        Get the current time from the database server.

        Returns:
            A timezone-aware datetime object representing the current
            time on the database server.
        """
        # Oh, but sqlite3 connection is, pylint: disable=not-context-manager
        with self:
            cursor = self.cursor()
            try:
                cursor.execute(
                    "SELECT strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')"
                )
                return dateutil.parser.isoparse(cursor.fetchone()[0])
            finally:
                cursor.close()


class Schema(AbstractSchema):
    """SQLite database schema v4.0"""

    # The connection class to use for talking to the database.
    Connection = Connection
    # The schema's version.
    version = (4, 0)
    # The I/O schema the database schema supports
    io = io.schema.V4_0

    # A map of table names and Table constructor arguments
    # For use by descendants
    TABLES_ARGS = dict(
        checkouts=dict(
            columns={
                "id": TextColumn(constraint=Constraint.PRIMARY_KEY),
                "origin": TextColumn(constraint=Constraint.NOT_NULL),
                "tree_name": TextColumn(),
                "git_repository_url": TextColumn(),
                "git_commit_hash": TextColumn(),
                "git_commit_name": TextColumn(),
                "git_repository_branch": TextColumn(),
                "patchset_files": JSONColumn(),
                "patchset_hash": TextColumn(),
                "message_id": TextColumn(),
                "comment": TextColumn(),
                "start_time": TimestampColumn(),
                "contacts": JSONColumn(),
                "log_url": TextColumn(),
                "log_excerpt": TextColumn(),
                "valid": BoolColumn(),
                "misc": JSONColumn(),
            }
        ),
        builds=dict(
            columns={
                "checkout_id": TextColumn(constraint=Constraint.NOT_NULL),
                "id": TextColumn(constraint=Constraint.PRIMARY_KEY),
                "origin": TextColumn(constraint=Constraint.NOT_NULL),
                "comment": TextColumn(),
                "start_time": TimestampColumn(),
                "duration": Column("REAL"),
                "architecture": TextColumn(),
                "command": TextColumn(),
                "compiler": TextColumn(),
                "input_files": JSONColumn(),
                "output_files": JSONColumn(),
                "config_name": TextColumn(),
                "config_url": TextColumn(),
                "log_url": TextColumn(),
                "log_excerpt": TextColumn(),
                "valid": BoolColumn(),
                "misc": JSONColumn(),
            }
        ),
        tests=dict(
            columns={
                "build_id": TextColumn(constraint=Constraint.NOT_NULL),
                "id": TextColumn(constraint=Constraint.PRIMARY_KEY),
                "origin": TextColumn(constraint=Constraint.NOT_NULL),
                "environment.comment": TextColumn(),
                "environment.misc": JSONColumn(),
                "path": TextColumn(),
                "comment": TextColumn(),
                "log_url": TextColumn(),
                "log_excerpt": TextColumn(),
                "status": TextColumn(),
                "waived": BoolColumn(),
                "start_time": TimestampColumn(),
                "duration": Column("REAL"),
                "output_files": JSONColumn(),
                "misc": JSONColumn()
            }
        ),
    )

    # A map of table names and schemas
    TABLES = {
        name: Table(**args) for name, args in TABLES_ARGS.items()
    }

    # Queries and their columns for each type of raw object-oriented data.
    # Both should have columns in the same order.
    OO_QUERIES = dict(
        revision=dict(
            statement="SELECT\n"
                      "    git_commit_hash,\n"
                      "    patchset_hash,\n"
                      "    patchset_files,\n"
                      "    git_commit_name\n"
                      "FROM checkouts\n"
                      "GROUP BY git_commit_hash, patchset_hash",
            schema=Table(dict(
                git_commit_hash=TextColumn(),
                patchset_hash=TextColumn(),
                patchset_files=JSONColumn(),
                git_commit_name=TextColumn(),
            )),
        ),
        checkout=dict(
            statement="SELECT\n"
                      "    id,\n"
                      "    git_commit_hash,\n"
                      "    NULL AS git_commit_tags,\n"
                      "    NULL AS git_commit_message,\n"
                      "    patchset_hash,\n"
                      "    origin,\n"
                      "    git_repository_url,\n"
                      "    git_repository_branch,\n"
                      "    NULL AS git_repository_branch_tip,\n"
                      "    tree_name,\n"
                      "    message_id,\n"
                      "    start_time,\n"
                      "    log_url,\n"
                      "    comment,\n"
                      "    valid,\n"
                      "    misc\n"
                      "FROM checkouts",
            schema=Table(dict(
                id=TextColumn(),
                git_commit_hash=TextColumn(),
                git_commit_tags=JSONColumn(),
                git_commit_message=TextColumn(),
                patchset_hash=TextColumn(),
                origin=TextColumn(),
                git_repository_url=TextColumn(),
                git_repository_branch=TextColumn(),
                git_repository_branch_tip=BoolColumn(),
                tree_name=TextColumn(),
                message_id=TextColumn(),
                start_time=TimestampColumn(),
                log_url=TextColumn(),
                comment=TextColumn(),
                valid=BoolColumn(),
                misc=JSONColumn(),
            )),
        ),
        build=dict(
            statement="SELECT\n"
                      "    id,\n"
                      "    checkout_id,\n"
                      "    origin,\n"
                      "    start_time,\n"
                      "    duration,\n"
                      "    architecture,\n"
                      "    command,\n"
                      "    compiler,\n"
                      "    input_files,\n"
                      "    output_files,\n"
                      "    config_name,\n"
                      "    config_url,\n"
                      "    log_url,\n"
                      "    comment,\n"
                      "    CASE valid\n"
                      "        WHEN TRUE THEN 'PASS'\n"
                      "        WHEN FALSE THEN 'FAIL'\n"
                      "        ELSE NULL\n"
                      "    END AS status,\n"
                      "    misc\n"
                      "FROM builds",
            schema=Table(dict(
                id=TextColumn(),
                checkout_id=TextColumn(),
                origin=TextColumn(),
                start_time=TimestampColumn(),
                duration=Column("REAL"),
                architecture=TextColumn(),
                command=TextColumn(),
                compiler=TextColumn(),
                input_files=JSONColumn(),
                output_files=JSONColumn(),
                config_name=TextColumn(),
                config_url=TextColumn(),
                log_url=TextColumn(),
                comment=TextColumn(),
                status=TextColumn(),
                misc=JSONColumn(),
            )),
        ),
        test=dict(
            statement="SELECT\n"
                      "    id,\n"
                      "    build_id,\n"
                      "    origin,\n"
                      "    path,\n"
                      "    \"environment.comment\" AS environment_comment,\n"
                      "    NULL AS environment_compatible,\n"
                      "    \"environment.misc\" AS environment_misc,\n"
                      "    log_url,\n"
                      "    status,\n"
                      "    NULL AS number_value,\n"
                      "    NULL AS number_unit,\n"
                      "    NULL AS number_prefix,\n"
                      "    start_time,\n"
                      "    duration,\n"
                      "    output_files,\n"
                      "    comment,\n"
                      "    misc\n"
                      "FROM tests",
            schema=Table(dict(
                id=TextColumn(),
                build_id=TextColumn(),
                origin=TextColumn(),
                path=TextColumn(),
                environment_comment=TextColumn(),
                environment_compatible=JSONColumn(),
                environment_misc=JSONColumn(),
                log_url=TextColumn(),
                status=TextColumn(),
                number_value=Column("REAL"),
                number_unit=TextColumn(),
                number_prefix=TextColumn(),
                start_time=TimestampColumn(),
                duration=Column("REAL"),
                output_files=JSONColumn(),
                comment=TextColumn(),
                misc=JSONColumn(),
            )),
        ),
        issue=dict(
            statement="SELECT\n"
                      "    NULL AS id,\n"
                      "    NULL AS origin\n"
                      "WHERE 0",
            schema=Table(dict(
                id=TextColumn(),
                origin=TextColumn()
            )),
        ),
        issue_version=dict(
            statement="SELECT\n"
                      "    NULL AS id,\n"
                      "    NULL AS version_num,\n"
                      "    NULL AS origin,\n"
                      "    NULL AS report_url,\n"
                      "    NULL AS report_subject,\n"
                      "    NULL AS culprit_code,\n"
                      "    NULL AS culprit_tool,\n"
                      "    NULL AS culprit_harness,\n"
                      "    NULL AS comment,\n"
                      "    NULL AS misc\n"
                      "WHERE 0",
            schema=Table(dict(
                id=TextColumn(),
                version_num=IntegerColumn(),
                origin=TextColumn(),
                report_url=TextColumn(),
                report_subject=TextColumn(),
                culprit_code=BoolColumn(),
                culprit_tool=BoolColumn(),
                culprit_harness=BoolColumn(),
                comment=TextColumn(),
                misc=JSONColumn(),
            )),
        ),
        incident=dict(
            statement="SELECT\n"
                      "    NULL AS id,\n"
                      "    NULL AS origin,\n"
                      "    NULL AS issue_id,\n"
                      "    NULL AS issue_version_num,\n"
                      "    NULL AS build_id,\n"
                      "    NULL AS test_id,\n"
                      "    NULL AS present,\n"
                      "    NULL AS comment,\n"
                      "    NULL AS misc\n"
                      "WHERE 0",
            schema=Table(dict(
                id=TextColumn(),
                origin=TextColumn(),
                issue_id=TextColumn(),
                issue_version_num=IntegerColumn(),
                build_id=TextColumn(),
                test_id=TextColumn(),
                present=BoolColumn(),
                comment=TextColumn(),
                misc=JSONColumn(),
            )),
        ),
    )

    def init(self):
        """
        Initialize the database. The database must be empty uninitialized.
        """
        with self.conn:
            cursor = self.conn.cursor()
            try:
                for table_name, table_schema in self.TABLES.items():
                    try:
                        cursor.execute(table_schema.format_create(table_name))
                    except Exception as exc:
                        raise Exception(
                            f"Failed creating table {table_name!r}"
                        ) from exc
            finally:
                cursor.close()

    def cleanup(self):
        """
        Cleanup (deinitialize) the database, removing all data.
        The database must be initialized.
        """
        with self.conn:
            cursor = self.conn.cursor()
            try:
                for name in self.TABLES:
                    cursor.execute(f"DROP TABLE IF EXISTS {name}")
            finally:
                cursor.close()

    def empty(self):
        """
        Empty the database, removing all data.
        The database must be initialized.
        """
        with self.conn:
            cursor = self.conn.cursor()
            try:
                for name, schema in self.TABLES.items():
                    cursor.execute(schema.format_delete(name))
            finally:
                cursor.close()

    def dump_iter(self, objects_per_report, with_metadata, after, until):
        """
        Dump all data from the database in object number-limited chunks.

        Args:
            objects_per_report: An integer number of objects per each returned
                                report data, or zero for no limit.
            with_metadata:      True, if metadata fields should be dumped as
                                well. False, if not.
            after:              A dictionary of names of I/O object types
                                (list names) and timezone-aware datetime
                                objects specifying the latest time the
                                corresponding objects should've arrived to be
                                *excluded* from the dump. Any objects which
                                arrived later will be *eligible* for dumping.
                                Object types missing from this dictionary will
                                not be limited.
            until:              A dictionary of names of I/O object types
                                (list names) and timezone-aware datetime
                                objects specifying the latest time the
                                corresponding objects should've arrived to be
                                *included* into the dump. Any objects which
                                arrived later will be *ineligible* for
                                dumping. Object types missing from this
                                dictionary will not be limited.

        Returns:
            An iterator returning report JSON data adhering to the I/O
            version of the database schema, each containing at most the
            specified number of objects.

        Raises:
            NoTimestamps    - Either "after" or "until" are not empty, and
                              the database doesn't have row timestamps.
        """
        assert isinstance(objects_per_report, int)
        assert objects_per_report >= 0
        assert isinstance(with_metadata, bool)

        obj_num = 0
        data = self.io.new()
        with self.conn:
            cursor = self.conn.cursor()
            try:
                for table_name, table_schema in self.TABLES.items():
                    result = cursor.execute(*table_schema.format_dump(
                        table_name, with_metadata,
                        after.get(table_name), until.get(table_name)
                    ))
                    obj_list = None
                    for obj in table_schema.unpack_iter(result,
                                                        with_metadata):
                        if obj_list is None:
                            obj_list = []
                            data[table_name] = obj_list
                        obj_list.append(obj)
                        obj_num += 1
                        if objects_per_report and \
                                obj_num >= objects_per_report:
                            assert self.io.is_compatible_exactly(data)
                            assert LIGHT_ASSERTS or \
                                self.io.is_valid_exactly(data)
                            yield data
                            obj_num = 0
                            data = self.io.new()
                            obj_list = None
            finally:
                cursor.close()

        if obj_num:
            assert self.io.is_compatible_exactly(data)
            assert LIGHT_ASSERTS or self.io.is_valid_exactly(data)
            yield data

    # We can live with this for now, pylint: disable=too-many-arguments
    # Or if you prefer, pylint: disable=too-many-positional-arguments
    def query_iter(self, ids, children, parents, objects_per_report,
                   with_metadata):
        """
        Match and fetch objects from the database, in object number-limited
        chunks.

        Args:
            ids:                A dictionary of object list names, and lists
                                of IDs of objects to match. Each ID is a tuple
                                of values. The values should match the types,
                                the order, and the number of the object's ID
                                fields as described by the database's I/O
                                schema (the "id_fields" attribute).
            children:           True if children of matched objects should be
                                matched as well.
            parents:            True if parents of matched objects should be
                                matched as well.
            objects_per_report: An integer number of objects per each returned
                                report data, or zero for no limit.
            with_metadata:      True, if metadata fields should be fetched as
                                well. False, if not.

        Returns:
            An iterator returning report JSON data adhering to the I/O version
            of the database schema, each containing at most the specified
            number of objects.
        """
        # Calm down, we'll get to it,
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-statements
        # pylint: disable=too-many-branches
        assert isinstance(objects_per_report, int)
        assert objects_per_report >= 0
        assert isinstance(with_metadata, bool)

        # A dictionary of object list (table) names, and "queries" returning
        # IDs of the objects to fetch. Each "query" is a tuple containing a
        # list of SELECT statement strings (to be joined with "UNION"), the
        # combined list of their parameters, and a tuple of ID field names.
        Query = namedtuple('Query', 'selects params fields')
        obj_list_queries = {
            obj_list_name: Query([], [], tuple(id_fields))
            for obj_list_name, id_fields in self.io.id_fields.items()
        }

        # For each name of object list and its query
        for obj_list_name, query in obj_list_queries.items():
            obj_list_ids = ids.get(obj_list_name, [])
            # If there are IDs specified for this object list
            if obj_list_ids:
                # Generate a SELECT returning the specified IDs
                # WITH ids(id) AS (VALUES ('abc'), ('def')) SELECT * FROM ids;
                query.selects.append(
                    "WITH ids(" + ", ".join(query.fields) + ") AS (VALUES\n" +
                    ",\n".join(
                        ["    (?" + ", ?" * (len(query.fields) - 1) + ")"] *
                        len(obj_list_ids)
                    ) +
                    "\n) SELECT * FROM ids\n"
                )
                query.params.extend(chain.from_iterable(obj_list_ids))

        def add_parents(obj_list_name):
            """Add parent IDs to query results"""
            obj_name = obj_list_name[:-1]
            query = obj_list_queries[obj_list_name]
            for child_list_name in self.io.graph[obj_list_name]:
                add_parents(child_list_name)
                child_query = obj_list_queries[child_list_name]
                if child_query.selects:
                    query.selects.append(
                        "SELECT " +
                        ", ".join(
                            f"{child_list_name}.{obj_name}_{f} AS {f}"
                            for f in query.fields
                        ) +
                        f" FROM {child_list_name} " +
                        "INNER JOIN (\n" +
                        textwrap.indent(
                            "UNION\n".join(child_query.selects),
                            " " * 4
                        ) +
                        ") AS ids USING(" +
                        ", ".join(child_query.fields) +
                        ")\n"
                    )
                    query.params.extend(child_query.params)
        # Add referenced parents if requested, starting from the graph source
        if parents:
            for obj_list_name in self.io.graph[""]:
                add_parents(obj_list_name)

        def add_children(obj_list_name):
            """Add child IDs to query results"""
            obj_name = obj_list_name[:-1]
            query = obj_list_queries[obj_list_name]
            for child_list_name in self.io.graph[obj_list_name]:
                if query.selects:
                    child_query = obj_list_queries[child_list_name]
                    child_query.selects.append(
                        "SELECT " + ", ".join(
                            f"{child_list_name}.{f} AS {f}"
                            for f in child_query.fields
                        ) + f" FROM {child_list_name} " +
                        "INNER JOIN (\n" +
                        textwrap.indent(
                            "UNION\n".join(query.selects),
                            " " * 4
                        ) +
                        f") AS {obj_list_name} ON " + " AND ".join(
                            f"{child_list_name}.{obj_name}_{f} = "
                            f"{obj_list_name}.{f}"
                            for f in query.fields
                        ) + "\n"
                    )
                    child_query.params.extend(query.params)
                add_children(child_list_name)
        # Add referenced children if requested, starting from the graph source
        if children:
            for obj_list_name in self.io.graph[""]:
                add_children(obj_list_name)

        # Fetch the data
        obj_num = 0
        data = self.io.new()
        with self.conn:
            cursor = self.conn.cursor()
            try:
                for obj_list_name, query in obj_list_queries.items():
                    if not query.selects:
                        continue
                    table_schema = self.TABLES[obj_list_name]
                    result = cursor.execute(
                        "SELECT " + ", ".join(
                            c.name for c in table_schema.columns.values()
                            if with_metadata or not c.schema.metadata_expr
                        ) + "\n" +
                        f"FROM {obj_list_name} INNER JOIN (\n" +
                        textwrap.indent(
                            "UNION\n".join(query.selects),
                            " " * 4
                        ) +
                        ") AS ids USING(" + ", ".join(query.fields) + ")\n",
                        query.params
                    )
                    obj_list = None
                    for obj in table_schema.unpack_iter(result,
                                                        with_metadata):
                        if obj_list is None:
                            obj_list = []
                            data[obj_list_name] = obj_list
                        obj_list.append(obj)
                        obj_num += 1
                        if objects_per_report and \
                                obj_num >= objects_per_report:
                            assert self.io.is_compatible_exactly(data)
                            assert LIGHT_ASSERTS or \
                                self.io.is_valid_exactly(data)
                            yield data
                            obj_num = 0
                            data = self.io.new()
                            obj_list = None
            finally:
                cursor.close()

        if obj_num:
            assert self.io.is_compatible_exactly(data)
            assert LIGHT_ASSERTS or self.io.is_valid_exactly(data)
            yield data

    @classmethod
    def _oo_query_render(cls, pattern):
        """
        Render a pattern for raw OO data into a query.

        Args:
            pattern:    The pattern (instance of kcidb.orm.query.Pattern) to
                        render.

        Returns:
            The SQL query string and the query parameters.
        """
        assert isinstance(pattern, orm.query.Pattern)
        obj_type = pattern.obj_type
        type_query_string = cls.OO_QUERIES[obj_type.name]["statement"]
        if pattern.obj_id_set:
            obj_id_field_types = obj_type.id_field_types
            query_string = "SELECT obj.* FROM (\n" + \
                textwrap.indent(type_query_string, " " * 4) + "\n" + \
                ") AS obj INNER JOIN (\n" + \
                "    WITH ids(" + \
                ", ".join(obj_id_field_types) + \
                ") AS (VALUES " + \
                ",\n".join(
                    [
                        "    (" +
                        ", ".join("?" * len(obj_id_field_types)) +
                        ")"
                    ] *
                    len(pattern.obj_id_set)
                ) + \
                ") SELECT * FROM ids\n" + \
                ") AS ids USING(" + ", ".join(obj_id_field_types) + ")"
            query_parameters = [
                obj_id_field
                for obj_id in pattern.obj_id_set
                for obj_id_field in obj_id
            ]
        else:
            query_string = type_query_string
            if pattern.obj_id_set is not None:
                # We cannot represent empty "VALUES"
                query_string += " WHERE 0"
            query_parameters = []

        if pattern.base:
            base_query_string, base_query_parameters = \
                cls._oo_query_render(pattern.base)
            base_obj_type = pattern.base.obj_type
            if pattern.child:
                column_pairs = zip(
                    base_obj_type.children[obj_type.name].ref_fields,
                    base_obj_type.id_field_types
                )
            else:
                column_pairs = zip(
                    obj_type.id_field_types,
                    obj_type.children[base_obj_type.name].ref_fields
                )

            query_string = "SELECT obj.* FROM (\n" + \
                textwrap.indent(query_string, " " * 4) + "\n" + \
                ") AS obj INNER JOIN (\n" + \
                textwrap.indent(base_query_string, " " * 4) + "\n" + \
                ") AS base ON " + \
                " AND ".join(
                    [f"obj.{o} = base.{b}" for o, b in column_pairs]
                )
            query_parameters += base_query_parameters

        return query_string, query_parameters

    def oo_query(self, pattern_set):
        """
        Query raw object-oriented data from the database.

        Args:
            pattern_set:    A set of patterns ("kcidb.orm.query.Pattern"
                            instances) matching objects to fetch.
        Returns:
            A dictionary of object type names and lists containing retrieved
            objects of the corresponding type.
        """
        assert isinstance(pattern_set, set)
        assert all(isinstance(r, orm.query.Pattern) for r in pattern_set)

        # Render all queries for each type
        obj_type_queries = {}
        for obj_type in orm.data.SCHEMA.types.values():
            for pattern in pattern_set:
                # TODO: Avoid adding the same patterns multiple times
                if pattern.obj_type == obj_type:
                    if obj_type not in obj_type_queries:
                        obj_type_queries[obj_type] = []
                    obj_type_queries[obj_type]. \
                        append(self._oo_query_render(pattern))

        # Execute all the queries
        with self.conn:
            cursor = self.conn.cursor()
            try:
                objs = {}
                for obj_type, queries in obj_type_queries.items():
                    query_string = "SELECT obj.* FROM (\n" + \
                        textwrap.indent(
                            self.OO_QUERIES[obj_type.name]["statement"],
                            "    "
                        ) + "\n" + \
                        ") AS obj INNER JOIN (\n" + \
                        "    SELECT DISTINCT " + \
                        ", ".join(obj_type.id_field_types) + \
                        " FROM (\n" + \
                        textwrap.indent(
                            "\nUNION ALL\n".join(q[0] for q in queries),
                            " " * 8
                        ) + "\n" + \
                        "    )\n" + \
                        ") AS ids USING(" + \
                        ", ".join(obj_type.id_field_types) + \
                        ")"
                    query_parameters = reduce(lambda x, y: x + y,
                                              (q[1] for q in queries))
                    objs[obj_type.name] = list(
                        self.OO_QUERIES[obj_type.name]["schema"].unpack_iter(
                            cursor.execute(query_string, query_parameters),
                            with_metadata=False,
                            drop_null=False
                        )
                    )
            finally:
                cursor.close()

        assert LIGHT_ASSERTS or orm.data.SCHEMA.is_valid(objs)
        return objs

    def load(self, data, with_metadata, copy):
        """
        Load data into the database.

        Args:
            data:           The JSON data to load into the database. Must
                            adhere to the I/O version of the database schema.
                            Will be modified, if "copy" is False.
            with_metadata:  True if any metadata in the data should
                            also be loaded into the database. False if it
                            should be discarded and the database should
                            generate its metadata itself.
            copy:           True, if the loaded data should be copied before
                            packing. False, if the loaded data should be
                            packed in-place.
        """
        assert self.io.is_compatible_directly(data)
        assert LIGHT_ASSERTS or self.io.is_valid_exactly(data)
        assert isinstance(with_metadata, bool)
        assert isinstance(copy, bool)
        with self.conn:
            cursor = self.conn.cursor()
            try:
                for table_name, table_schema in self.TABLES.items():
                    if table_name in data:
                        cursor.executemany(
                            table_schema.format_insert(
                                table_name, self.conn.load_prio_db,
                                with_metadata
                            ),
                            table_schema.pack_iter(data[table_name],
                                                   with_metadata)
                        )
            finally:
                cursor.close()
        # Flip priority for the next load to maintain (rough)
        # parity with non-determinism of BigQuery's ANY_VALUE()
        self.conn.load_prio_db = not self.conn.load_prio_db

    def get_first_modified(self):
        """
        Get the time data has arrived first into the driven database.
        The database must be initialized.

        Returns:
            A dictionary of names of I/O object types (list names), which have
            objects in the database, and timezone-aware datetime objects
            representing the time the first one has arrived into the database.

        Raises:
            NoTimestamps    - The database doesn't have row timestamps, and
                              cannot determine data arrival time.
        """
        query = reduce(
            lambda a, b: (a[0] + "\nUNION ALL\n" + b[0], a[1] + b[1]),
            (
                table_schema.format_get_first_modified(table_name)
                for table_name, table_schema in self.TABLES.items()
            )
        )
        with self.conn:
            cursor = self.conn.cursor()
            try:
                return {
                    table_name: dateutil.parser.isoparse(first_modified)
                    for (table_name, first_modified)
                    in cursor.execute(*query)
                    if first_modified
                }
            finally:
                cursor.close()

    def get_last_modified(self):
        """
        Get the time data has arrived last into the driven database.
        The database must be initialized.

        Returns:
            A dictionary of names of I/O object types (list names), which have
            objects in the database, and timezone-aware datetime objects
            representing the time the last one has arrived into the database.

        Raises:
            NoTimestamps    - The database doesn't have row timestamps, and
                              cannot determine data arrival time.
        """
        query = reduce(
            lambda a, b: (a[0] + "\nUNION ALL\n" + b[0], a[1] + b[1]),
            (
                table_schema.format_get_last_modified(table_name)
                for table_name, table_schema in self.TABLES.items()
            )
        )
        with self.conn:
            cursor = self.conn.cursor()
            try:
                return {
                    table_name: dateutil.parser.isoparse(last_modified)
                    for (table_name, last_modified)
                    in cursor.execute(*query)
                    if last_modified
                }
            finally:
                cursor.close()
