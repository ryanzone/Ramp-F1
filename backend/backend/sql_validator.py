"""SQL validation for the analytics engine.

Only SELECT/WITH over the `replay.*` views is ever executed. The check is done on the
parsed syntax tree (sqlglot), not on text, and the query that is executed is the
re-generated normalised SQL, never the original string, so there is no parser
differential to smuggle anything through. Rules:

  * exactly one statement, a SELECT (CTEs, set operations and subqueries allowed)
  * no INTO, locking clauses, DML/DDL anywhere (also nested in CTEs), no commands
  * tables: only CTE names or views in the catalog (unqualified or `replay.`)
  * columns must exist (checked with sqlglot's qualifier against the catalog)
  * functions: allow-list only (no set_config, pg_sleep, dblink, file access, ...)
  * values enter only as named placeholders (`:name`), bound by the driver

The database enforces the same boundary independently (read-only role, replay views,
clock secret); this module is defence in depth and gives readable error messages.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError, SqlglotError
from sqlglot.optimizer.qualify import qualify

MAX_SQL_LENGTH = 8000
SCHEMA = 'replay'


class SqlValidationError(ValueError):
    """The query is not allowed or does not match the schema."""


ALLOWED_FUNC_TYPES = (
    exp.Avg, exp.Sum, exp.Count, exp.Min, exp.Max, exp.Stddev, exp.StddevSamp, exp.StddevPop,
    exp.Variance, exp.VariancePop, exp.Round, exp.Abs, exp.Ceil, exp.Floor, exp.Coalesce, exp.Nullif,
    exp.Greatest, exp.Least, exp.RowNumber, exp.Rank, exp.DenseRank, exp.Lag, exp.Lead, exp.FirstValue,
    exp.LastValue, exp.Ntile, exp.NthValue, exp.Extract, exp.DateTrunc, exp.Lower, exp.Upper, exp.Length,
    exp.Concat, exp.ConcatWs, exp.Substring, exp.Cast, exp.TryCast, exp.Case, exp.If, exp.GroupConcat,
    exp.PercentileCont, exp.PercentileDisc, exp.Pow, exp.Sqrt, exp.Trim, exp.Between, exp.In,
    exp.RegexpLike, exp.RegexpILike, exp.CumeDist, exp.PercentRank, exp.Timestamp, exp.TimestampDiff,
)
ALLOWED_FUNC_TYPES += tuple(getattr(exp, n) for n in ('RegrSlope', 'RegrIntercept', 'RegrR2', 'Corr', 'CovarSamp', 'CovarPop')
                            if hasattr(exp, n))
ALLOWED_ANONYMOUS = {
    'regr_slope', 'regr_intercept', 'regr_r2', 'corr', 'string_agg', 'percentile_cont', 'percentile_disc',
    'median', 'bool_and', 'bool_or', 'count_if', 'make_interval', 'date_part', 'trunc', 'sign',
    'cume_dist', 'percent_rank',
}
FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter, exp.Command,
    exp.Set, exp.Copy, exp.Transaction, exp.Commit, exp.Rollback, exp.Use, exp.Pragma, exp.Into,
    exp.Lock, exp.Grant, exp.Describe, exp.TruncateTable,
)
ROOTS = (exp.Select, exp.Union, exp.Except, exp.Intersect)
_PLACEHOLDER = re.compile(r'^[a-z_][a-z0-9_]*$')


@dataclass
class Validated:
    sql: str                                  # normalised, driver-ready (%(name)s placeholders)
    params: set[str]                          # placeholder names the query needs
    tables: set[str]                          # replay views referenced
    features: dict = field(default_factory=dict)


def _is_operator(node) -> bool:
    return isinstance(node, (exp.Binary, exp.Unary, exp.Connector, exp.Predicate, exp.Paren))


def _check_function(node) -> None:
    if _is_operator(node) or isinstance(node, ALLOWED_FUNC_TYPES) or isinstance(node, exp.AggFunc):
        # AggFunc covers the usual aggregates; the explicit tuple handles named windows etc.
        if isinstance(node, exp.AggFunc) and not isinstance(node, ALLOWED_FUNC_TYPES) \
                and not isinstance(node, exp.Anonymous):
            raise SqlValidationError(f'aggregate {type(node).__name__.upper()} is not allowed')
        return
    if isinstance(node, exp.Anonymous):
        if node.name.lower() in ALLOWED_ANONYMOUS:
            return
        raise SqlValidationError(f'function {node.name}() is not allowed')
    raise SqlValidationError(f'function {type(node).__name__.upper()} is not allowed')


def validate(sql: str, catalog: dict[str, dict[str, str]], params: set[str] | None = None) -> Validated:
    """Validate and normalise `sql`. `catalog` maps view -> {column: type}; `params` are the
    placeholder names the caller will bind (every placeholder in the query must be among them)."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlValidationError('empty query')
    if len(sql) > MAX_SQL_LENGTH:
        raise SqlValidationError('query is too long')
    try:
        trees = [t for t in sqlglot.parse(sql, read='postgres') if t is not None]
    except (ParseError, SqlglotError) as exc:
        raise SqlValidationError(f'cannot parse query: {str(exc).splitlines()[0]}') from None
    if len(trees) != 1:
        raise SqlValidationError('exactly one statement is allowed')
    tree = trees[0]
    if not isinstance(tree, ROOTS):
        raise SqlValidationError('only SELECT queries are allowed')

    for node in tree.walk():
        node = node[0] if isinstance(node, tuple) else node
        if isinstance(node, FORBIDDEN_NODES):
            raise SqlValidationError(f'{type(node).__name__.upper()} is not allowed; queries are read-only')

    # ---- tables ---------------------------------------------------------------------
    cte_names = {c.alias.lower() for c in tree.find_all(exp.CTE)}
    tables: set[str] = set()
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise SqlValidationError('table-valued functions are not allowed')
        if table.args.get('catalog'):
            raise SqlValidationError('cross-database references are not allowed')
        name, schema = table.name.lower(), (table.db or '').lower()
        if not schema and name in cte_names:
            continue
        if schema not in ('', SCHEMA):
            raise SqlValidationError(f'schema {table.db!r} is not accessible; use the replay views')
        if name not in catalog:
            raise SqlValidationError(f'unknown table {table.name!r}; available: {", ".join(sorted(catalog))}')
        tables.add(name)

    # ---- functions --------------------------------------------------------------------
    for func in tree.find_all(exp.Func):
        _check_function(func)

    # ---- columns (the qualifier raises on unknown columns) ----------------------------
    probe = tree.copy()
    for table in probe.find_all(exp.Table):
        if table.db and table.name.lower() not in cte_names:
            table.set('db', None)
    try:
        qualify(probe, schema={t: {c: ty for c, ty in cols.items()} for t, cols in catalog.items()},
                dialect='postgres', validate_qualify_columns=True, identify=False)
    except OptimizeError as exc:
        raise SqlValidationError(f'column check failed: {exc}') from None
    except SqlglotError as exc:
        raise SqlValidationError(f'query is not valid: {str(exc).splitlines()[0]}') from None

    # ---- placeholders + normalisation --------------------------------------------------
    found = {p.name for p in tree.find_all(exp.Placeholder)}
    for name in found:
        if not name or not _PLACEHOLDER.match(name):
            raise SqlValidationError(f'bad placeholder {name!r}; use :lower_case_names')
    if params is not None and found - params:
        raise SqlValidationError(f'no value supplied for: {", ".join(sorted(found - params))}')

    final = tree.copy()
    for table in final.find_all(exp.Table):
        if table.name.lower() not in cte_names or table.db:
            table.set('db', exp.to_identifier(SCHEMA))
    final = final.transform(lambda n: exp.Var(this=f'__P_{n.name}__') if isinstance(n, exp.Placeholder) else n)
    text = final.sql(dialect='postgres', comments=False).replace('%', '%%')
    text = re.sub(r'__P_([a-z_][a-z0-9_]*)__', r'%(\1)s', text)

    features = {
        'joins': len(list(tree.find_all(exp.Join))),
        'ctes': len(cte_names),
        'window_functions': len(list(tree.find_all(exp.Window))),
        'group_by': tree.find(exp.Group) is not None,
        'having': tree.find(exp.Having) is not None,
        'subqueries': len(list(tree.find_all(exp.Subquery))),
        'aggregates': len(list(tree.find_all(exp.AggFunc))),
        'case_expressions': len(list(tree.find_all(exp.Case))),
        'set_operations': len(list(tree.find_all(exp.Union, exp.Except, exp.Intersect))),
    }
    return Validated(sql=text, params=found, tables=tables, features=features)
