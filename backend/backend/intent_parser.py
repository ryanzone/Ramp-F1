"""Rule-based question understanding (no LLM): intent, entities and follow-up context."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from backend.sql_generator import INTENT_BY_NAME, INTENTS, Entities, Intent, suggestions

MAX_QUESTION_LENGTH = 500
WORD_NUMBERS = {w: i for i, w in enumerate(
    'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen twenty'.split())}
WORD_NUMBERS['twenty'] = 20
# Three-letter driver codes that are ordinary English words: only accepted when written in capitals.
AMBIGUOUS_CODES = {'per', 'law', 'gas', 'had', 'bot', 'col', 'ant', 'ham', 'bea', 'lin', 'sai', 'bor'}
ORDINALS = {'first': 0, '1st': 0, 'second': 1, '2nd': 1, 'runner-up': 1, 'runner up': 1, 'runnerup': 1,
            'third': 2, '3rd': 2, 'fourth': 3, '4th': 3, 'fifth': 4, '5th': 4}
ORDINAL_RE = re.compile(r'\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|runner[- ]?up)\b')
FOLLOWUP_RE = re.compile(r'^\s*(and|what about|how about|same for|now|also)\b')
PRONOUN_RE = re.compile(r'\b(he|him|his|she|her|they|them|their|that driver|this driver|the same driver)\b')
COMPOUNDS = {'soft': 'SOFT', 'softs': 'SOFT', 'medium': 'MEDIUM', 'mediums': 'MEDIUM', 'hard': 'HARD', 'hards': 'HARD',
             'inter': 'INTERMEDIATE', 'inters': 'INTERMEDIATE', 'intermediate': 'INTERMEDIATE',
             'intermediates': 'INTERMEDIATE', 'wet': 'WET', 'wets': 'WET'}
GENERIC_TEAM_WORDS = {'racing', 'team', 'f1', 'the'}


def strip_accents(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))


@dataclass
class Context:
    """What the analyst remembers between questions of one replay."""
    last_intent: str | None = None
    last_rows: list[dict] = field(default_factory=list)
    subject: dict | None = None                      # the driver "he/him" refers to
    last_drivers: list[dict] = field(default_factory=list)


@dataclass
class Parsed:
    intent: Intent | None
    entities: Entities
    used_context: list[str] = field(default_factory=list)
    clarification: str | None = None                 # a question back to the user
    message: str | None = None                       # explanation when no intent matched
    suggestions: list[str] = field(default_factory=list)


# ---- entity extraction ------------------------------------------------------------------------
def _driver_matches(question: str, roster: list[dict]) -> list[dict]:
    plain = strip_accents(question)
    low = plain.lower()
    found: list[tuple[int, dict]] = []

    def add(pos, driver):
        if all(d['driver_code'] != driver['driver_code'] for _, d in found):
            found.append((pos, driver))

    by_number = {d['driver_number']: d for d in roster}
    for m in re.finditer(r'(?:\bcar\s*|\bnumber\s*|\bno\.?\s*|#)(\d{1,2})\b', low):
        if int(m.group(1)) in by_number:
            add(m.start(), by_number[int(m.group(1))])
    for d in roster:
        code = d['driver_code']
        if not code:
            continue
        m = re.search(rf'\b{re.escape(code)}\b', plain)                 # capitals: always a code
        if not m and code.lower() not in AMBIGUOUS_CODES:
            m = re.search(rf'\b{re.escape(code.lower())}\b', low)
        if m:
            add(m.start(), d)
        name = strip_accents(d['driver_name'] or '')
        tokens = [t for t in re.split(r'[\s-]+', name) if t]
        surname = [t for t in tokens if t.isupper()] or tokens[-1:]
        words = [t.lower() for t in surname if len(t) >= 3] + [t.lower() for t in tokens[:1] if len(t) >= 4]
        for w in words:
            m = re.search(rf'\b{re.escape(w)}\b', low)
            if m:
                add(m.start(), d)
    return [d for _, d in sorted(found, key=lambda x: x[0])]


def _team_matches(question: str, roster: list[dict]) -> list[str]:
    low = strip_accents(question).lower()
    hits: list[tuple[int, str]] = []
    for team in sorted({d['team_name'] for d in roster if d.get('team_name')}):
        name = strip_accents(team).lower()
        words = [w for w in name.split() if w not in GENERIC_TEAM_WORDS]
        candidates = {name, ' '.join(words), name.replace(' ', '')} | {w for w in words if len(w) >= 5}
        if name == 'red bull racing':
            candidates |= {'red bull', 'redbull'}
        for c in sorted(candidates, key=len, reverse=True):
            m = re.search(rf'\b{re.escape(c)}\b', low) if c else None
            if m:
                hits.append((m.start(), team))
                break
    return [t for _, t in sorted(hits)]


def _number(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return WORD_NUMBERS.get(token)


def _extract_numbers(low: str, e: Entities) -> None:
    m = re.search(r'(?:last|past|previous|recent|final)\s+(\w+)\s+minutes?', low)
    if m and (n := _number(m.group(1))):
        e.minutes = n
    m = re.search(r'(?:last|past|previous|recent|final)\s+(\w+)\s+(?:clean\s+)?laps?', low) or \
        re.search(r'(?:top|first)\s+(\w+)', low)
    if m and (n := _number(m.group(1))):
        e.n = n
    if e.n:
        e.n = min(e.n, 60)
    if e.minutes:
        e.minutes = min(e.minutes, 240)
    m = re.search(r'\b(\w+)\s+minutes?\b', low)
    if not e.minutes and m and (n := _number(m.group(1))):
        e.minutes = min(n, 240)


def extract_entities(question: str, roster: list[dict]) -> Entities:
    low = strip_accents(question).lower()
    e = Entities(drivers=_driver_matches(question, roster), teams=_team_matches(question, roster))
    _extract_numbers(low, e)
    for word, compound in COMPOUNDS.items():
        if re.search(rf'\b{word}\b', low):
            e.compound = compound
            break
    if re.search(r'\b(lost|lose|losing places|dropped|worst|biggest loser|fell|fallen)\b', low):
        e.flags.add('lost')
    return e


# ---- intent choice + follow-ups ----------------------------------------------------------------------
def _pick_intent(low: str) -> Intent | None:
    for intent in INTENTS:
        if any(p.search(low) for p in intent.patterns):
            return intent
    return None


def ordinal_index(word: str) -> int:
    spaced = word.replace('-', ' ')
    return ORDINALS.get(word, ORDINALS.get(spaced, ORDINALS.get(spaced.replace(' ', ''), 0)))


def _lookup(roster: list[dict], code: str | None) -> dict | None:
    return next((d for d in roster if d['driver_code'] == code), None)


def _row_driver(row: dict) -> str | None:
    for key in ('driver_code', 'chaser', 'attacker'):
        if row.get(key):
            return row[key]
    return None


def subject_from_rows(rows: list[dict]) -> str | None:
    return _row_driver(rows[0]) if rows else None


def parse(question: str, roster: list[dict], context: Context | None = None) -> Parsed:
    context = context or Context()
    question = (question or '').strip()
    if not question:
        return Parsed(None, Entities(), message='Ask a question about the race, for example: ' + suggestions(1)[0],
                      suggestions=suggestions())
    if len(question) > MAX_QUESTION_LENGTH:
        return Parsed(None, Entities(), message=f'Please keep the question under {MAX_QUESTION_LENGTH} characters.')

    low = strip_accents(question).lower()
    entities = extract_entities(question, roster)
    used: list[str] = []

    # Follow-ups: "him" -> the driver of the last answer; "the second-fastest" -> row 2 of the last answer.
    ordinal = ORDINAL_RE.search(low)
    if ordinal and context.last_rows:
        idx = ordinal_index(ordinal.group(1))
        if idx < len(context.last_rows):
            d = _lookup(roster, _row_driver(context.last_rows[idx]))
            if d and all(x['driver_code'] != d['driver_code'] for x in entities.drivers):
                entities.drivers.append(d)
                used.append(f"{ordinal.group(1)} in the previous answer = {d['driver_code']}")
    if PRONOUN_RE.search(low) and context.subject:
        if all(x['driver_code'] != context.subject['driver_code'] for x in entities.drivers):
            entities.drivers.insert(0, context.subject)
            used.append(f"him/her = {context.subject['driver_code']} (from the previous answer)")

    intent = _pick_intent(low)
    # "and NOR?" / "what about HAM?" repeats the previous analysis for another driver.
    if (intent is None or intent.name == 'driver_summary') and entities.drivers and FOLLOWUP_RE.search(low) \
            and context.last_intent in INTENT_BY_NAME and len(low.split()) <= 5:
        intent = INTENT_BY_NAME[context.last_intent]
        used.append(f'repeating the previous analysis ({intent.title})')
    if intent is None and entities.drivers and not entities.teams and len(low.split()) <= 4:
        intent = INTENT_BY_NAME['driver_summary']                    # just a driver's name
    if intent is None:
        return Parsed(None, entities, message="I can't map that question to an analysis yet.",
                      suggestions=suggestions())

    if intent.name == 'penalty_reason' and not entities.drivers:
        intent = INTENT_BY_NAME['penalties_list']
    if intent.name == 'compare_drivers' and len(entities.drivers) == 1 and context.subject \
            and entities.drivers[0]['driver_code'] != context.subject['driver_code']:
        entities.drivers.insert(0, context.subject)
        used.append(f"compared with {context.subject['driver_code']} (from the previous answer)")
    if intent.name == 'compare_drivers' and len(entities.drivers) < 2 and entities.teams:
        intent = INTENT_BY_NAME['compare_team_strategies']

    if len(entities.drivers) < intent.needs_drivers:
        example = ', '.join(d['driver_code'] for d in roster[:3])
        need = 'two drivers' if intent.needs_drivers == 2 else 'a driver'
        return Parsed(intent, entities, used, clarification=(
            f'Which {need} do you mean? Use a name or code, for example {example}.'))
    if intent.needs_drivers == 1:
            entities.drivers = entities.drivers[:1]
    elif intent.needs_drivers >= 2:
        entities.drivers = entities.drivers[:5]

    return Parsed(intent, entities, used)
