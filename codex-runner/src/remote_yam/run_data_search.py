"""Cached full-text public run lookup. No network, model, media or private fields."""
from collections import defaultdict
from functools import lru_cache
import re
import time

from .run_search import _terms, _RELATED_GROUPS

_STOP = set("""all any there here task tasks happened happen morning woke wake one know roughly
    about tell data library different prompt prompts annotations examples example
    look looking looked search searched searching show list find found match matches
    mention mentioned includes contain contains entire whole every also only then
    than not no none cant cannot t don dont s what which when where why who much
    more another actually really just same before after result results works work
    fails fail success failure compare model models please could""".split())
_ALIASES = {term: group[0] for group in _RELATED_GROUPS for term in group}
_ALIASES.update(dict.fromkeys('cam cams cameras'.split(), 'camera'))
_ALIASES.update(dict.fromkeys('unplug unpluged unplugged unplugging detached detach detaching disconnect disconnected disconnecting'.split(), 'disconnect'))
_ALIASES.update({'removed':'remove','removing':'remove','cables':'cable','cord':'cable','wire':'cable','wires':'cable'})
_ACTIONS = set('disconnect remove pick grasp grab lift put place insert drop deposit move transfer carry stack pile'.split())
_MODIFIERS = set('left right both red green blue black white small big'.split())
_LOOKUP = re.compile(r'\b(find|search|look|show|list|mention|prompts?|unplug\w*|detach\w*|disconnect\w*)\b|\b(?:is|was|were|are) there\b|\bwhich runs?\b', re.I)


def tokens(text):
    return tuple(dict.fromkeys(_ALIASES.get(word, word) for word in _terms(text)
        if word not in _STOP and not word.isdigit()))


def query_terms(question, history):
    terms = list(tokens(question))
    # Resolve "unplugged it" / "look at all of them" from the latest user topic.
    # A new explicit subject replaces the previous topic.
    if not set(terms) - _ACTIONS - _MODIFIERS:
        for message in reversed(history):
            if message['role'] != 'user':
                continue
            previous = tokens(message['content'])
            if set(previous) - _ACTIONS - _MODIFIERS:
                terms += list(previous)
                break
    return tuple(dict.fromkeys(terms))[:24]


@lru_cache(maxsize=2)
def _index(documents):
    postings = defaultdict(set)
    fields = []
    for number, (_, _, prompt, annotation) in enumerate(documents):
        words = (frozenset(tokens(prompt)), frozenset(tokens(annotation)))
        fields.append(words)
        for word in words[0] | words[1]:
            postings[word].add(number)
    return dict(postings), fields


def _snippet(text, terms):
    # Anchor on the rarest matched concept, even beyond the model's excerpt limit.
    for term in terms:
        for match in re.finditer(r'[^\W_]+', text):
            if term in tokens(match.group()):
                start = max(0, match.start() - 75)
                end = min(len(text), start + 260)
                return ('…' if start else '') + text[start:end] + ('…' if end < len(text) else '')
    return text[:260]


def search_documents(documents, question, history):
    started = time.perf_counter()
    postings, fields = _index(documents)
    terms = query_terms(question, history)
    meaningful = tuple(t for t in terms if t not in _MODIFIERS)
    candidates = set.intersection(*(postings.get(t, set()) for t in meaningful)) if meaningful else set()
    mode = 'all_terms'
    if meaningful and not candidates:
        mode = 'partial'
        subjects = tuple(t for t in meaningful if t not in _ACTIONS)
        required = subjects or meaningful
        candidates = set.intersection(*(postings.get(t, set()) for t in required))
        if not candidates:
            candidates = set.union(*(postings.get(t, set()) for t in required))
    ordered_terms = sorted(terms, key=lambda t:len(postings.get(t, ())))
    def score(number):
        prompt, annotation = fields[number]
        return (sum((1 if t in _MODIFIERS or (t in _ACTIONS and t != 'disconnect') else 4) for t in terms if t in prompt | annotation),
                sum(1 for t in terms if t in prompt), -number)
    ordered = sorted(candidates, key=score, reverse=True)
    hits = []
    for number in ordered[:32]:
        eid, robot, prompt, annotation = documents[number]
        matched = [t for t in ordered_terms if t in fields[number][0] | fields[number][1]]
        source = 'prompt' if any(t in fields[number][0] for t in matched if t not in _MODIFIERS) else 'annotation'
        hits.append(dict(episode_id=eid, robot_id=robot, search_match=dict(
            terms=matched, field=source, snippet=_snippet(prompt if source == 'prompt' else annotation, matched))))
    meta = dict(query_terms=list(terms), searched_runs=len(documents), matched_runs=len(ordered),
        records_returned=len(hits), match_mode=mode, fields=['full prompt','saved annotation'],
        match_basis='Normalized words, spelling variants and related task terms; not a semantic guarantee',
        elapsed_ms=round((time.perf_counter()-started)*1000, 2))
    return meta, hits


def lookup_answer(context, question, history):
    """Return simple lookups immediately; leave analysis/comparisons to the model."""
    search = context['search']
    lookup = bool(_LOOKUP.search(question))
    if not lookup and re.search(r'\b(all|more|another|those|them)\b', question, re.I):
        lookup = any(_LOOKUP.search(m['content']) for m in history if m['role'] == 'user')
    if re.search(r'\b(success\w*|fail\w*|mixed|compare|rate|percent|pattern\w*)\b', question, re.I) and not re.search(r'\b(search|prompt\w*|mention\w*)\b', question, re.I):
        lookup = False
    if not lookup:
        return None
    if not search['query_terms']:
        return dict(answer=f"I can search all {search['searched_runs']:,} full prompts and saved annotations in this scope. What task or terms would you like to find?", citations=[],provider='local_search',model_called=False,requested_model=None,resolved_model=None,visual_evidence_received=False)
    from urllib.parse import urlencode
    total, matched = search['searched_runs'], search['matched_runs']
    rows = [r for r in context['evidence'] if r.get('search_match')][:8]
    search['records_returned'] = len(rows)
    terms = ', '.join(search['query_terms'])
    if matched:
        qualifier = 'matching all search terms' if search['match_mode'] == 'all_terms' else 'matching some search terms (related results)'
        answer = f'I searched the full prompts and saved annotations of all {total:,} runs in this scope. Found {matched:,} text matches {qualifier} for “{terms}”; showing {len(rows)}.\n\nA matching prompt records what was requested, not proof of what physically happened. Open the supporting replays to check the outcome.'
    else:
        answer = f'I searched the full prompts and saved annotations of all {total:,} runs in this scope for “{terms}” and found no text matches. This does not rule out an incident visible only in recordings; no videos were inspected.'
    citations = [dict(episode_id=r['episode_id'],robot_id=r['robot_id'],prompt=r['prompt'],label=r['label'],
        note=f"{r['search_match']['field'].capitalize()} match: {r['search_match']['snippet']}",
        url='/?'+urlencode({'robot_id':r['robot_id'],'run':r['episode_id']})+'#past-runs') for r in rows]
    return dict(answer=answer,citations=citations,provider='local_search',model_called=False,
        requested_model=None,resolved_model=None,visual_evidence_received=False)
