"""Conservative SEC earnings-exhibit and inline-XBRL readers.

Discovery metadata never substitutes for a dated earnings release. Unsupported
layouts remain pending; no heuristic calendar fiscal identity or adjusted EPS.
"""
import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from lxml import html

MONTH = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)'
DATE = MONTH + r'\s+\d{1,2},?\s+\d{4}'
QUARTERS = {'first':1, 'second':2, 'third':3, 'fourth':4, '1st':1, '2nd':2, '3rd':3, '4th':4}
REVENUE_TAGS = {'us-gaap:Revenues', 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax', 'us-gaap:SalesRevenueNet',
                'us-gaap:RevenuesNetOfInterestExpense', 'us-gaap:RevenueNotFromContractWithCustomer'}


def normalize_proxy_base(value):
    raw = (value or '').strip().rstrip('/')
    if not raw:
        return ''
    if '://' not in raw:
        raw = 'https://' + raw
    try:
        p = urlparse(raw)
        valid = (p.scheme == 'https' and p.hostname and '.' in p.hostname
                 and re.fullmatch(r'[A-Za-z0-9.-]+', p.hostname) and not p.username and not p.password
                 and p.port in (None, 443) and not p.query and not p.fragment and p.path in ('', '/'))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Invalid SEC proxy configuration; use an HTTPS origin without credentials or path')
    return raw


def _text(tree):
    return ' '.join(tree.itertext()).replace('\xa0', ' ')


def _date(text):
    cleaned = text.replace('.', '').replace(',', '')
    cleaned = re.sub(r'\bSept\b', 'Sep', cleaned)
    for fmt in ('%B %d %Y', '%b %d %Y'):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass
    raise ValueError('Unsupported explicit release date')


def parse_earnings_release(document, event_date, filing_date, today):
    tree = html.fromstring(document)
    for node in tree.xpath('//script|//style'):
        node.drop_tree()
    text = ' '.join(_text(tree).split())
    intro = text[:3000]
    if not re.search(r'(?i)\b(?:results|earnings)\b', intro):
        raise ValueError('Not an earnings release')
    event, filed = date.fromisoformat(event_date), date.fromisoformat(filing_date)
    # The SEC event date is merely a candidate; original exhibit must explicitly confirm it.
    intro_dates = {_date(m[0]) for m in re.finditer(DATE, intro, re.I)}
    if event not in intro_dates or not event <= filed <= today:
        raise ValueError('Original earnings exhibit does not confirm release date')
    periods = [m[1] for m in re.finditer(r'(?i)(?:quarter|three\s+months)\s+ended\s+(' + DATE + ')', text)]
    ends = {_date(p) for p in periods if _date(p) < event}
    if not ends:
        raise ValueError('No explicit completed quarterly period')
    end = max(ends)
    if (event - end).days > 180:
        raise ValueError('Release period is not current for this event')
    identity = re.search(r'(?i)\b(first|second|third|fourth|1st|2nd|3rd|4th)[\s-]+quarter\s+(?:of\s+)?(?:fiscal\s+)?(20\d{2})\b', intro)
    if identity is None:
        identity = re.search(r'(?i)\bQ([1-4])\s+(?:FY\s*)?(20\d{2})\b', intro)
        fiscal_quarter = int(identity[1]) if identity else None
    else:
        fiscal_quarter = QUARTERS[identity[1].lower()]
    return {'date': event.isoformat(), 'periodEnd': end.isoformat(),
            'fiscalYear': int(identity[2]) if identity else None, 'fiscalQuarter': fiscal_quarter}


def _local(node):
    return str(node.tag).lower().split('}')[-1].split(':')[-1]


def _desc(node, local):
    return [n for n in node.iter() if _local(n) == local]


def _unique_text(nodes):
    values = {' '.join(_text(n).split()) for n in nodes}
    return values.pop() if len(values) == 1 else None


def parse_inline_quarter(document, period_end):
    tree = html.fromstring(document)
    nodes = list(tree.iter())
    def dei(tag):
        return _unique_text(n for n in nodes if n.get('name', '').lower() == 'dei:' + tag.lower())
    if dei('DocumentPeriodEndDate') != period_end:
        raise ValueError('Official document period does not match release period')
    year, focus = dei('DocumentFiscalYearFocus'), dei('DocumentFiscalPeriodFocus')
    if not year or not year.isdigit() or focus not in ('Q1','Q2','Q3','FY'):
        raise ValueError('Explicit fiscal-year/quarter focus unavailable')
    contexts = {}
    for context in (n for n in nodes if _local(n) == 'context'):
        if _desc(context, 'segment') or _desc(context, 'scenario'):
            continue
        start = _unique_text(_desc(context, 'startdate'))
        end = _unique_text(_desc(context, 'enddate'))
        if start and end == period_end:
            duration = (date.fromisoformat(end)-date.fromisoformat(start)).days + 1
            # Explicit DEI fiscal focus plus a short dimensionless duration is required.
            if 70 <= duration <= 110:
                contexts[context.get('id')] = start
    units = {}
    for unit in (n for n in nodes if _local(n) == 'unit'):
        numerator = _desc(unit, 'unitnumerator')
        denominator = _desc(unit, 'unitdenominator')
        if numerator and denominator:
            if (_unique_text(_desc(numerator[0], 'measure')) or '').lower() == 'iso4217:usd' and (_unique_text(_desc(denominator[0], 'measure')) or '').lower() == 'xbrli:shares':
                units[unit.get('id')] = 'USD/shares'
        elif (_unique_text(_desc(unit, 'measure')) or '').lower() == 'iso4217:usd':
            units[unit.get('id')] = 'USD'
    eps, revenue, starts = set(), set(), set()
    for node in nodes:
        if _local(node) != 'nonfraction' or node.get('contextref') not in contexts:
            continue
        tag = node.get('name', '')
        is_eps = tag.lower() == 'us-gaap:earningspersharediluted'
        is_revenue = tag.lower() in {t.lower() for t in REVENUE_TAGS}
        if not is_eps and not is_revenue:
            continue
        if units.get(node.get('unitref')) != ('USD/shares' if is_eps else 'USD'):
            continue
        if node.get('format', '').split(':')[-1] not in ('', 'num-dot-decimal', 'numdotdecimal'):
            continue
        try:
            raw = ''.join(_text(node).split()).replace(',', '')
            if not re.fullmatch(r'\d+(?:\.\d+)?', raw):
                continue
            scale = int(node.get('scale', '0'))
            if not -12 <= scale <= 15:
                continue
            value = Decimal(raw) * Decimal(10) ** scale
            if node.get('sign') == '-':
                value = -value
            if not value.is_finite() or (is_revenue and value < 0):
                continue
        except (ValueError, InvalidOperation):
            continue
        (eps if is_eps else revenue).add(float(value))
        starts.add(contexts[node.get('contextref')])
    return {'fiscalYear':int(year), 'fiscalQuarter':4 if focus == 'FY' else int(focus[-1]),
            'periodScope':'quarter', 'periodEnd':period_end,
            'periodStart': next(iter(starts)) if len(starts)==1 else None,
            'epsGaapDiluted':next(iter(eps)) if len(eps)==1 else None,
            'revenue':next(iter(revenue)) if len(revenue)==1 else None,
            'epsBasis':'GAAP diluted', 'currency':'USD'}
