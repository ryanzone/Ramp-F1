import unittest

from backend.sql_validator import SqlValidationError, validate

CATALOG = {
    'laps': {'driver_code': 'text', 'driver_name': 'text', 'team_name': 'text', 'lap_number': 'int',
             'lap_time_seconds': 'numeric', 'lap_end_at': 'timestamptz', 'is_valid': 'boolean'},
    'drivers': {'driver_code': 'text', 'driver_number': 'int', 'team_name': 'text'},
    'race_control': {'recorded_at': 'timestamptz', 'message': 'text', 'driver_code': 'text', 'lap_number': 'int'},
}


def bad(sql, fragment=None, params=None):
    def run(self):
        with self.assertRaises(SqlValidationError) as cm:
            validate(sql, CATALOG, params)
        if fragment:
            self.assertIn(fragment.lower(), str(cm.exception).lower())
    return run


class AcceptTests(unittest.TestCase):
    def test_rich_query_with_every_feature(self):
        v = validate("""
            WITH recent AS (
                SELECT driver_code, lap_time_seconds,
                       ROW_NUMBER() OVER (PARTITION BY driver_code ORDER BY lap_number DESC) AS recency
                FROM laps WHERE is_valid AND lap_time_seconds IS NOT NULL)
            SELECT r.driver_code, d.team_name, ROUND(AVG(r.lap_time_seconds), 3) AS avg_lap,
                   RANK() OVER (ORDER BY AVG(r.lap_time_seconds)) AS pace_rank,
                   CASE WHEN COUNT(*) >= :min_laps THEN 'ok' ELSE 'few' END AS sample
            FROM recent r JOIN drivers d ON d.driver_code = r.driver_code
            WHERE r.recency <= :n AND d.team_name ILIKE :team
              AND r.lap_time_seconds > (SELECT MIN(lap_time_seconds) FROM laps)
            GROUP BY r.driver_code, d.team_name HAVING COUNT(*) >= 3
            ORDER BY avg_lap LIMIT 10""", CATALOG, {'min_laps', 'n', 'team'})
        f = v.features
        self.assertEqual((f['ctes'], f['joins'], f['group_by'], f['having']), (1, 1, True, True))
        self.assertGreaterEqual(f['window_functions'], 2)
        self.assertGreaterEqual(f['subqueries'], 1)
        self.assertEqual(v.params, {'min_laps', 'n', 'team'})
        self.assertEqual(v.tables, {'laps', 'drivers'})

    def test_normalised_sql_is_schema_qualified_and_uses_driver_placeholders(self):
        v = validate("SELECT driver_code FROM laps WHERE lap_number > :n AND driver_code ILIKE :pat", CATALOG)
        self.assertIn('replay.laps', v.sql)
        self.assertIn('%(n)s', v.sql)
        self.assertIn('%(pat)s', v.sql)
        self.assertNotIn(':n', v.sql)

    def test_replay_prefix_union_and_literal_percent(self):
        v = validate("SELECT driver_code FROM replay.laps WHERE driver_code LIKE '%X%' "
                     "UNION SELECT driver_code FROM replay.drivers", CATALOG)
        self.assertEqual(v.features['set_operations'], 1)
        self.assertIn('%%X%%', v.sql)                       # escaped for the driver

    def test_comments_are_harmless_and_dropped(self):
        v = validate("SELECT /* hi */ driver_code FROM laps -- trailing", CATALOG)
        self.assertNotIn('hi', v.sql)


class RejectTests(unittest.TestCase):
    test_empty = bad('   ', 'empty')
    test_not_string = bad(None, 'empty')
    test_two_statements = bad('SELECT 1; SELECT 2', 'one statement')
    test_drop_after_select = bad('SELECT 1; DROP TABLE laps', 'one statement')
    test_delete = bad('DELETE FROM laps', 'only select')
    test_update = bad("UPDATE laps SET lap_number = 1", 'only select')
    test_insert = bad("INSERT INTO laps(lap_number) VALUES (1)", 'only select')
    test_drop = bad('DROP TABLE laps', None)
    test_alter = bad('ALTER TABLE laps ADD COLUMN x int', None)
    test_create = bad('CREATE TABLE x AS SELECT 1', None)
    test_truncate = bad('TRUNCATE laps', None)
    test_grant = bad('GRANT ALL ON laps TO PUBLIC', None)
    test_set = bad("SET search_path = public", None)
    test_reset_role = bad('RESET ROLE', None)
    test_copy = bad("COPY laps TO '/tmp/x'", None)
    test_select_into = bad('SELECT * INTO newtable FROM laps', 'not allowed')
    test_for_update = bad('SELECT * FROM laps FOR UPDATE', 'not allowed')
    test_nested_dml_in_cte = bad('WITH x AS (DELETE FROM laps RETURNING *) SELECT * FROM x', 'read-only')
    test_unknown_table = bad('SELECT * FROM secrets', 'unknown table')
    test_base_table_by_schema = bad('SELECT * FROM public.laps', 'not accessible')
    test_catalog_schema = bad('SELECT * FROM pg_catalog.pg_user', 'not accessible')
    test_information_schema = bad('SELECT * FROM information_schema.tables', 'not accessible')
    test_cross_database = bad('SELECT * FROM otherdb.public.laps', 'cross-database')
    test_unknown_column = bad('SELECT nope FROM laps', 'column')
    test_unknown_qualified_column = bad('SELECT l.nope FROM laps l', 'column')
    test_table_function = bad('SELECT * FROM generate_series(1, 100000000)', 'not allowed')
    test_pg_sleep = bad('SELECT pg_sleep(30)', 'pg_sleep')
    test_set_config = bad("SELECT set_config('x', 'y', false)", 'set_config')
    test_current_setting = bad("SELECT current_setting('x')", 'current_setting')
    test_set_clock = bad("SELECT replay.set_clock('a', 1, now())", 'not allowed')
    test_dblink = bad("SELECT * FROM dblink('x', 'select 1') AS t(a int)", None)
    test_file_read = bad("SELECT pg_read_file('/etc/passwd')", 'pg_read_file')
    test_lo_import = bad("SELECT lo_import('/etc/passwd')", 'lo_import')
    test_hidden_in_subquery = bad('SELECT (SELECT pg_sleep(5)) FROM laps', 'pg_sleep')
    test_hidden_in_cte = bad('WITH x AS (SELECT pg_sleep(5)) SELECT * FROM x', 'pg_sleep')
    test_unlisted_aggregate = bad('SELECT xmlagg(xmlelement(name a)) FROM laps', None)
    test_missing_param = bad('SELECT driver_code FROM laps WHERE lap_number > :n', 'no value supplied', set())
    test_too_long = bad('SELECT 1 ' + 'FROM laps ' * 1000, 'too long')
    test_garbage = bad('SELEC FROM WHERE ((', None)

    def test_injection_strings_in_comments_and_quotes_stay_inert(self):
        # Values never go into SQL text, so quotes/semicolons in a *literal* are just data.
        v = validate("SELECT driver_code FROM laps WHERE driver_code = 'x''; DROP TABLE laps; --'", CATALOG)
        self.assertEqual(v.features['joins'], 0)
        self.assertIn("'x''; DROP TABLE laps; --'", v.sql)   # still one string literal, not a statement

    def test_dollar_quoting_and_unicode_tricks_do_not_hide_statements(self):
        for sql in ("SELECT $$ x $$; DROP TABLE laps", "SELECT 1 /*; DROP TABLE laps*/; DELETE FROM laps",
                    "SELECT ; DROP TABLE laps"):
            with self.assertRaises(SqlValidationError):
                validate(sql, CATALOG)


if __name__ == '__main__':
    unittest.main()
