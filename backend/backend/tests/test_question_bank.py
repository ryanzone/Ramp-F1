"""Every question the Pit Wall UI suggests (frontend/src/PitWall.jsx) must be answerable."""
import re
import unittest
from pathlib import Path

from backend.intent_parser import Context, parse

PITWALL = Path(__file__).resolve().parents[3] / 'frontend' / 'src' / 'PitWall.jsx'

ROSTER = [
    dict(driver_number=1, driver_code='NOR', driver_name='Lando NORRIS', team_name='McLaren'),
    dict(driver_number=3, driver_code='VER', driver_name='Max VERSTAPPEN', team_name='Red Bull Racing'),
    dict(driver_number=44, driver_code='HAM', driver_name='Lewis HAMILTON', team_name='Ferrari'),
]


def suggested_questions() -> list[str]:
    source = PITWALL.read_text(encoding='utf-8')
    found = []
    for _title, body in re.findall(r'title: "([^"]+)",\s*questions: \[(.*?)\]', source, re.S):
        found += re.findall(r'"([^"]+)"', body)
    return found


class QuestionBankTest(unittest.TestCase):
    def test_bank_is_not_empty(self):
        self.assertGreater(len(suggested_questions()), 20)

    def test_every_suggested_question_maps_to_an_intent_without_clarification(self):
        problems = []
        for q in suggested_questions():
            parsed = parse(q, ROSTER, Context())
            if parsed.intent is None or parsed.clarification:
                problems.append(q)
        self.assertEqual(problems, [], 'suggested questions the analyst cannot answer')

    def test_pit_time_questions_are_not_treated_as_pace_questions(self):
        for q, intent in [('Which driver lost the most time in the pits?', 'pit_time_lost'),
                          ('Who is losing time?', 'losing_time'),
                          ('Which driver has had the most pit stops?', 'pit_counts')]:
            self.assertEqual(parse(q, ROSTER, Context()).intent.name, intent, q)

    def test_lowercase_nor_is_the_word_not_the_driver(self):
        self.assertEqual(parse('neither this nor that is fast', ROSTER, Context()).entities.drivers, [])
        self.assertEqual([d['driver_code'] for d in parse('How is NOR doing?', ROSTER, Context()).entities.drivers], ['NOR'])


if __name__ == '__main__':
    unittest.main()
