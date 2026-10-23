"""Rank public task prompts with explicit related terms, without model calls.

Related objects help discover evidence; they are not equivalent capabilities.
Only catalog prompts are indexed, never private runner logs or visitor data.
"""
import re
import unicodedata

MAX_QUERY_LENGTH = 300
_STOP_WORDS = set('''a an the to into in on onto at of for from with and or it its
    this that these those is are was were be been being can could would should
    will do does did able ability whether how i me my we you your robot robots
    please try trying attempt attempts previous past run runs find search show
    have has had up down some stuff something'''.split())
_RELATED_GROUPS = (
    ('pen', 'marker', 'pencil', 'highlighter', 'crayon'),
    ('cup', 'mug', 'beaker', 'tumbler', 'glass'),
    ('block', 'cube', 'brick'),
    ('ball', 'sphere'),
    ('bowl', 'dish', 'plate'),
    ('cloth', 'towel', 'rag'),
    ('pick', 'grasp', 'grab', 'lift'),
    ('put', 'place', 'insert', 'drop', 'deposit'),
    ('move', 'transfer', 'carry'),
    ('stack', 'pile'),
)
_RELATED = {term: frozenset(group) for group in _RELATED_GROUPS for term in group}
_ACTIONS = set('pick grasp grab lift put place insert drop deposit move transfer carry stack pile'.split())
_MODIFIERS = set('red blue green yellow orange purple pink black white gray grey brown small large big little left right both'.split())
_FORMS = {
    'picked': 'pick', 'picking': 'pick', 'grasped': 'grasp', 'grasping': 'grasp',
    'grabbed': 'grab', 'grabbing': 'grab', 'lifted': 'lift', 'lifting': 'lift',
    'putting': 'put', 'placed': 'place', 'placing': 'place',
    'inserted': 'insert', 'inserting': 'insert', 'dropped': 'drop', 'dropping': 'drop',
    'deposited': 'deposit', 'depositing': 'deposit', 'moved': 'move', 'moving': 'move',
    'transferred': 'transfer', 'transferring': 'transfer', 'carried': 'carry', 'carrying': 'carry',
    'stacked': 'stack', 'stacking': 'stack', 'piled': 'pile', 'piling': 'pile',
    'glasses': 'glass',
}


def _terms(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    terms = []
    for word in re.findall(r'[^\W_]+', text):
        if word in _STOP_WORDS:
            continue
        word = _FORMS.get(word, word)
        if len(word) > 4 and word.endswith('ies'):
            word = word[:-3] + 'y'
        elif len(word) > 4 and word.endswith(('xes', 'ches', 'shes')):
            word = word[:-2]
        elif len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
            word = word[:-1]
        if word not in terms:
            terms.append(word)
    return terms


def rank_runs(rows, query):
    """Return copies with match explanations; ties preserve newest-first order.

    Object/other task terms weigh more than actions. If a query includes objects,
    an action alone cannot qualify a result. Partial task matches are intentional.
    """
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError('Search is too long')
    terms = _terms(query)[:32]
    subjects = set(terms) - _ACTIONS - _MODIFIERS
    ranked = []
    for row in rows:
        words = set(_terms(row.get('prompt', '')))
        exact, related = [], []
        coverage = exact_weight = 0
        for term in terms:
            alternatives = words & _RELATED.get(term, frozenset({term}))
            if not alternatives:
                continue
            weight = 1 if term in _ACTIONS or term in _MODIFIERS else 3
            coverage += weight
            if term in words:
                exact.append(term)
                exact_weight += weight
            else:
                related.append({'query': term, 'match': sorted(alternatives)[0]})
        matched = set(exact) | {pair['query'] for pair in related}
        if not matched or (subjects and not subjects & matched):
            continue
        match = {'exact': exact, 'related': related, 'partial': len(matched) < len(terms)}
        ranked.append(((coverage, exact_weight), dict(row, search_match=match)))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in ranked]
