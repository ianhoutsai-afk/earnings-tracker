"""Explicit official release schedules; conference calls remain separate events."""
import re
from datetime import timedelta
from lxml import html
from official_sources import DATE, _date

def parse_expected_release(document, today):
    tree = html.fromstring(document.encode('utf-8') if isinstance(document,str) else document)
    for node in tree.xpath('//script|//style'):
        node.drop_tree()
    text = ' '.join(' '.join(tree.itertext()).split())
    candidates = {}
    for match in re.finditer(r'(?i)\bwill\s+(?:post|report|release|announce|publish)\s+(.{0,100}?)\bfinancial\s+results\b', text):
        if re.search(r'(?i)preliminary|product|\band\b|conference|\bcall\b', match[1]):
            continue
        tail = text[match.end():match.end()+300]
        when = re.search(DATE, tail, re.I)
        if when is None:
            continue
        before = tail[:when.start()]
        if re.search(r'(?i)conference|\bcall\b|webcast|preliminary|\band\b|[.!?]\s+[A-Z]', before):
            continue
        day = _date(when[0])
        if not today <= day <= today+timedelta(days=180):
            continue
        # Timing may immediately follow the date; do not borrow it from a later call.
        after = re.match(r'(?i)\s*,?\s*((?:after (?:the )?market clos(?:e|es)|before (?:the )?market open(?:s)?))\b', tail[when.end():])
        timing_text = before + (' ' + after[1] if after else '')
        timing = 'AMC' if re.search(r'(?i)after (?:the )?market clos(?:e|es)',timing_text) else 'BMO' if re.search(r'(?i)before (?:the )?market open(?:s)?',timing_text) else None
        candidates[day.isoformat()] = {'date':day.isoformat(),'bmo_amc':timing,'eventType':'earnings_release'}
    return next(iter(candidates.values())) if len(candidates)==1 else None
