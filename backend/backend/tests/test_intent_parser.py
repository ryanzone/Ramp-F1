import unittest

from backend.intent_parser import Context, parse
from backend.sql_generator import INTENTS

ROSTER = [
    {'driver_number': 3, 'driver_code': 'VER', 'driver_name': 'Max VERSTAPPEN', 'team_name': 'Red Bull Racing'},
    {'driver_number': 1, 'driver_code': 'NOR', 'driver_name': 'Lando NORRIS', 'team_name': 'McLaren'},
    {'driver_number': 44, 'driver_code': 'HAM', 'driver_name': 'Lewis HAMILTON', 'team_name': 'Ferrari'},
    {'driver_number': 16, 'driver_code': 'LEC', 'driver_name': 'Charles LECLERC', 'team_name': 'Ferrari'},
    {'driver_number': 30, 'driver_code': 'LAW', 'driver_name': 'Liam LAWSON', 'team_name': 'Racing Bulls'},
    {'driver_number': 11, 'driver_code': 'PER', 'driver_name': 'Sergio PÉREZ', 'team_name': 'Cadillac'},
    {'driver_number': 12, 'driver_code': 'ANT', 'driver_name': 'Andrea Kimi ANTONELLI', 'team_name': 'Mercedes'},
    {'driver_number': 63, 'driver_code': 'RUS', 'driver_name': 'George RUSSELL', 'team_name': 'Mercedes'},
]


def codes(parsed):
    return [d['driver_code'] for d in parsed.entities.drivers]


class IntentChoiceTests(unittest.TestCase):
    CASES = {
        'Who currently has the fastest average lap time?': 'fastest_avg',
        'Who has the best race pace?': 'fastest_avg',
        'Who is the fastest?': 'fastest_avg',
        'What is the fastest lap so far?': 'fastest_lap',
        'Which driver has been most consistent?': 'consistency',
        'Which driver has the strongest race pace over the last five laps?': 'recent_pace',
        'Who gained the most positions?': 'positions_gained',
        'Who lost the most places?': 'positions_gained',
        'Compare VER and NOR race pace': 'compare_drivers',
        'Which drivers are currently running on hard tyres?': 'tyres_now',
        'Who is on softs?': 'tyres_now',
        'Who has the highest tyre degradation?': 'tyre_degradation',
        'Which drivers could benefit from an undercut?': 'undercut',
        'Compare tyre strategies between constructors': 'compare_team_strategies',
        'Compare Ferrari and Mercedes tyre strategy': 'compare_team_strategies',
        'Show the tyre stints': 'tyre_stints',
        'Which team has the fastest average pit stops?': 'pit_team_avg',
        'How many pit stops has each driver completed?': 'pit_counts',
        'Which drivers have not pitted yet?': 'not_pitted',
        "Which drivers haven't stopped yet?": 'not_pitted',
        'Analyse the time lost during pit stops': 'pit_time_lost',
        'Identify drivers losing significant time': 'losing_time',
        'Who is losing pace?': 'losing_time',
        'Identify potential overtake opportunities': 'overtakes',
        'Who has been penalised?': 'penalties_list',
        'Why did NOR get a penalty?': 'penalty_reason',
        'Is Hamilton under investigation?': 'penalty_reason',
        'What is the weather like?': 'weather',
        'Is there a safety car?': 'race_status',
        'What is the race status?': 'race_status',
        'What lap is it?': 'current_lap',
        'How is VER doing?': 'driver_summary',
        'Who is leading?': 'standings',
        'Show the standings': 'standings',
        'What happened in the last 10 minutes?': 'recent_events',
        'Show the position progression': 'position_history',
        'Compare qualifying performance against race performance': 'qualifying_vs_race',
        'What is the gap between VER and NOR?': 'gap_between',
    }

    def test_phrasings(self):
        wrong = {}
        for q, expected in self.CASES.items():
            got = parse(q, ROSTER).intent
            if got is None or got.name != expected:
                wrong[q] = got.name if got else None
        self.assertEqual(wrong, {})

    def test_every_registered_example_parses_to_its_own_intent(self):
        wrong = {}
        for intent in INTENTS:
            for example in intent.examples:
                parsed = parse(example, ROSTER, Context(subject=ROSTER[0], last_rows=[{'driver_code': 'VER'}, {'driver_code': 'NOR'}]))
                got = parsed.intent.name if parsed.intent else None
                # two-driver examples without names are valid only through follow-up context
                if got != intent.name:
                    wrong[example] = got
        self.assertEqual(wrong, {})

    def test_unsupported_questions_get_suggestions_not_guesses(self):
        for q in ('What is the meaning of life?', 'Tell a joke', 'xyzzy', 'Will it rain tomorrow in Paris'):
            p = parse(q, ROSTER)
            if p.intent is not None and p.intent.name != 'weather':
                self.fail(f'{q!r} matched {p.intent.name}')
        p = parse('What is the meaning of life?', ROSTER)
        self.assertIsNone(p.intent)
        self.assertGreater(len(p.suggestions), 3)

    def test_empty_and_overlong_questions(self):
        self.assertIsNone(parse('   ', ROSTER).intent)
        self.assertIn('500', parse('x' * 501, ROSTER).message)


class EntityTests(unittest.TestCase):
    def test_drivers_by_code_surname_first_name_and_number(self):
        self.assertEqual(codes(parse('Compare VER and NOR race pace', ROSTER)), ['VER', 'NOR'])
        self.assertEqual(codes(parse('compare verstappen with norris', ROSTER)), ['VER', 'NOR'])
        self.assertEqual(codes(parse('compare Lando and Lewis', ROSTER)), ['NOR', 'HAM'])
        self.assertEqual(codes(parse('why did car 44 get a penalty', ROSTER)), ['HAM'])
        self.assertEqual(codes(parse('How is Pérez doing?', ROSTER)), ['PER'])
        self.assertEqual(codes(parse('how is perez doing', ROSTER)), ['PER'])

    def test_order_follows_the_question(self):
        self.assertEqual(codes(parse('Compare NOR and VER', ROSTER)), ['NOR', 'VER'])

    def test_english_words_are_not_driver_codes(self):
        self.assertEqual(codes(parse('what is the pace per lap', ROSTER)), [])
        self.assertEqual(codes(parse('is there a law about this', ROSTER)), [])
        self.assertEqual(codes(parse('Why did LAW get a penalty?', ROSTER)), ['LAW'])      # capitals = code

    def test_teams_numbers_compounds(self):
        p = parse('Compare Ferrari and Red Bull tyre strategy', ROSTER)
        self.assertEqual(p.entities.teams, ['Ferrari', 'Red Bull Racing'])
        self.assertEqual(parse('pace over the last 8 laps', ROSTER).entities.n, 8)
        self.assertEqual(parse('pace over the last five laps', ROSTER).entities.n, 5)
        self.assertEqual(parse('what happened in the last 15 minutes', ROSTER).entities.minutes, 15)
        self.assertEqual(parse('who is on hard tyres', ROSTER).entities.compound, 'HARD')
        self.assertEqual(parse('who is on intermediates', ROSTER).entities.compound, 'INTERMEDIATE')
        self.assertIn('lost', parse('who lost the most places', ROSTER).entities.flags)

    def test_numbers_are_capped(self):
        self.assertEqual(parse('pace over the last 9999 laps', ROSTER).entities.n, 60)


class ClarificationAndContextTests(unittest.TestCase):
    def test_missing_drivers_ask_a_question_back(self):
        p = parse('Compare race pace', ROSTER)
        self.assertIsNotNone(p.clarification)
        self.assertIn('two drivers', p.clarification)
        p = parse('How is he doing?', ROSTER)
        self.assertIn('driver', p.clarification)

    def test_penalty_question_without_a_driver_lists_all_penalties(self):
        self.assertEqual(parse('Any penalties?', ROSTER).intent.name, 'penalties_list')

    def test_follow_up_him_and_second_fastest(self):
        ctx = Context(last_intent='fastest_avg', subject=ROSTER[1],
                      last_rows=[{'driver_code': 'NOR'}, {'driver_code': 'VER'}, {'driver_code': 'LEC'}])
        p = parse('Compare him with the second-fastest', ROSTER, ctx)
        self.assertEqual(p.intent.name, 'compare_drivers')
        self.assertEqual(codes(p), ['NOR', 'VER'])
        self.assertTrue(p.used_context)

    def test_follow_up_third_and_runner_up(self):
        ctx = Context(subject=ROSTER[0], last_rows=[{'driver_code': 'VER'}, {'driver_code': 'NOR'}, {'driver_code': 'HAM'}])
        self.assertEqual(codes(parse('Compare him with the third', ROSTER, ctx)), ['VER', 'HAM'])
        self.assertEqual(codes(parse('Compare him with the runner-up', ROSTER, ctx)), ['VER', 'NOR'])

    def test_pronoun_uses_the_previous_subject(self):
        ctx = Context(subject=ROSTER[2], last_rows=[{'driver_code': 'HAM'}])
        p = parse('Why did he get a penalty?', ROSTER, ctx)
        self.assertEqual((p.intent.name, codes(p)), ('penalty_reason', ['HAM']))

    def test_explicit_driver_with_a_remembered_subject_compares_the_two(self):
        ctx = Context(subject=ROSTER[0], last_rows=[{'driver_code': 'VER'}])
        p = parse('compare with NOR', ROSTER, ctx)
        self.assertEqual(codes(p), ['VER', 'NOR'])

    def test_short_follow_up_repeats_the_last_analysis(self):
        ctx = Context(last_intent='tyre_degradation', last_rows=[])
        p = parse('and NOR?', ROSTER, ctx)
        self.assertEqual(p.intent.name, 'tyre_degradation')

    def test_just_a_driver_name_gives_a_summary(self):
        self.assertEqual(parse('Norris', ROSTER).intent.name, 'driver_summary')

    def test_context_is_not_shared_between_calls(self):
        parse('Compare him with the second', ROSTER, Context(subject=ROSTER[0], last_rows=[{'driver_code': 'VER'}, {'driver_code': 'NOR'}]))
        p = parse('Compare him with the second', ROSTER, Context())
        self.assertIsNotNone(p.clarification)


if __name__ == '__main__':
    unittest.main()
