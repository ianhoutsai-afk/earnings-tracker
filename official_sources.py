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
DATE = r'(?:'+MONTH+r'\s+\d{1,2}\s*,?\s+\d{4}|\d{1,2}\s+'+MONTH+r'\s+\d{4})'
QUARTERS = {'first':1, 'second':2, 'third':3, 'fourth':4, '1st':1, '2nd':2, '3rd':3, '4th':4}
REVENUE_TAGS = {'us-gaap:Revenues', 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax', 'us-gaap:SalesRevenueNet',
                'us-gaap:RevenuesNetOfInterestExpense'}


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
    if not isinstance(tree.tag, str):
        return ''
    return ' '.join(tree.itertext()).replace('\xa0', ' ')


def _date(text):
    cleaned = text.replace('.', '').replace(',', '')
    cleaned = re.sub(r'\bSept\b', 'Sep', cleaned)
    for fmt in ('%B %d %Y', '%b %d %Y','%d %B %Y','%d %b %Y'):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass
    raise ValueError('Unsupported explicit release date')


def _fiscal_identity(intro):
    identity_text = re.split(r'(?i)all comparisons|compared (?:to|with)|forward-looking|forecasting|\boutlook\b',intro)[0]
    patterns = [
        r'(?i)\b(first|second|third|fourth|1st|2nd|3rd|4th)[\s-]+quarter[\s-]+(?:and[\s-]+(?:full[\s-]+)?(?:fiscal[\s-]+)?year[\s-]+)?(?:of[\s-]+)?(?:fiscal[\s-]+)?(?:year[\s-]+)?(20\d{2})\b',
        r'(?i)\bQ([1-4])\s+(?:FY\s*)?(20\d{2})\b',
        r'(?i)\b(20\d{2})[\s-]+(first|second|third|fourth)[\s-]+quarter\b',
    ]
    matches=[(m.start(),int(m[2]),int(m[1]) if m[1].isdigit() else QUARTERS[m[1].lower()]) for p in patterns[:2] for m in re.finditer(p,identity_text)]
    matches += [(m.start(),int(m[1]),QUARTERS[m[2].lower()]) for m in re.finditer(patterns[2],identity_text)]
    matches += [(m.start(),int('20'+m[2]) if len(m[2])==2 else int(m[2]),int(m[1])) for m in re.finditer(r'(?i)\b([1-4])Q\s*(20\d{2}|\d{2})\b',identity_text)]
    return min(matches)[1:] if matches else (None,None)


def _completed_period_end(text, event):
    periods = [m[1] for m in re.finditer(r'(?i)(?:quarter(?:\s+and\s+(?:(?:for\s+(?:the\s+)?)?(?:full[\s-]+)?(?:fiscal\s+)?year|(?:six|nine)\s+months))?|three(?:\s+and\s+(?:six|nine))?\s+months)\s+ended\s+(' + DATE + ')', text)]
    ends = {_date(p) for p in periods if _date(p) < event}
    return max(ends) if ends else None


def parse_earnings_release(document, event_date, filing_date, today):
    tree = html.fromstring(document.encode('utf-8') if isinstance(document, str) else document)
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
    end = _completed_period_end(text,event)
    # The dated results sentence can state a standalone quarter and its
    # cumulative period together before naming their shared period end.
    reported_half = re.search(
        r'(?i)\b(?:reported|announced)\s+(?:financial\s+)?results\s+for\s+(?:its|the)\s+'
        r'second\s+quarter\s+and\s+'
        r'first\s+half\s+of\s+fiscal\s+(?P<year>20\d{2}),?\s+ended\s+(?P<end>' + DATE + ')',
        intro,
    )
    prior_dates = list(re.finditer(DATE, intro[:reported_half.start()], re.I)) if reported_half else []
    if prior_dates and _date(prior_dates[-1][0]) == event:
        confirmed_end = _date(reported_half['end'])
        if not 0 < (event - confirmed_end).days <= 180:
            raise ValueError('Release period is not current for this event')
        return {'date':event.isoformat(),'periodEnd':confirmed_end.isoformat(),
                'fiscalYear':int(reported_half['year']),
                'fiscalQuarter':2}
    completed_opening = re.search(
        r'(?i)\btoday\s+(?:reported|announced|released)\s+(?:(?:its|the)\s+)?'
        r'(?:financial\s+)?results\s+for\s+the\s+'
        r'(?:first|second|third|fourth|1st|2nd|3rd|4th)[\s-]+quarter\s+ending\s+(' + DATE + ')',
        intro,
    )
    if completed_opening:
        publication_dates = list(re.finditer(DATE, intro[:completed_opening.start()], re.I))
        if publication_dates and _date(publication_dates[-1][0]) == event:
            end = _date(completed_opening[1])
            if end >= event:
                raise ValueError('Earnings period has not ended')
    # Fiscal identity comes from the current release, never a calendar guess.
    year,fiscal_quarter=_fiscal_identity(intro)
    if end is not None and (event - end).days > 180:
        raise ValueError('Release period is not current for this event')
    if end is None:
        # Some actual-results releases put the period only in the later financial
        # tables. The dated, completed-results sentence and explicit fiscal focus
        # can join a matching 10-Q/10-K. No filing means no new quarter is admitted.
        actual = re.search(r'(?i)\b(?:reported|announced|released)\s+(?:(?:its|the)\s+)?(?:financial\s+)?results\s+for\b',intro)
        malformed_period = re.search(r'(?i)\b(?:quarter|months)\s+ended\b', text)
        if not actual or year is None or fiscal_quarter is None or malformed_period:
            raise ValueError('No explicit completed quarterly period')
        publication_dates = [m for m in re.finditer(DATE, intro[:actual.start()], re.I)]
        if not publication_dates or _date(publication_dates[-1][0]) != event:
            raise ValueError('Candidate date does not attest completed publication')
        end = None
    return {'date': event.isoformat(), 'periodEnd': end.isoformat() if end else None,
            'fiscalYear':year, 'fiscalQuarter':fiscal_quarter}


def parse_earnings_filing(document,event_date,filing_date,today,exhibit=None):
    """An explicit Item 2.02 publication statement is release evidence, not its cover date."""
    tree=html.fromstring(document.encode('utf-8') if isinstance(document,str) else document)
    # Keep block boundaries so a nearby footnote cannot become part of a publication.
    for node in tree.iter():
        if _local(node) in ('p','div','tr','h1','h2','h3','h4'):
            node.tail=(node.tail or '')+'\n'
    text='\n'.join(' '.join(line.split()) for line in _text(tree).splitlines() if line.strip())
    sections=re.findall(r'(?is)\bItem\s*2\.02\b(.*?)(?=\bItem\s*(?!(?:2\.02|7\.01)\b)\d+\.\d+\b|\bSIGNATURES?\b|$)',text)
    if not sections:raise ValueError('No earnings publication statement')
    section=' '.join(' '.join(sections).split())
    statements=list(re.finditer(r'(?i)\bOn\s+(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?('+DATE+r')\s*,?\s+(.{0,350}?(?:reported|announced|issued|released|posted)\b.{0,250})',section))
    statements += list(re.finditer(r'(?i)\b(?:announced|reported)\s+on\s+('+DATE+r')(.{0,400})',section))
    statements += list(re.finditer(r'(?i)(?:press|news)\s+release(?:(?!'+DATE+r').){0,150}?(?:dated|issued(?:\s+by.{0,100}?)?\s+on)\s+('+DATE+r')(.{0,400})',section))
    statements += list(re.finditer(r'(?i)('+DATE+r')\s+press\s+release(.{0,400})',section))
    statements += list(re.finditer(r'(?i)\b(?:first|second|third|fourth)[\s-]+quarter\s+20\d{2}\s+earnings\s+release\b.{0,220}?\bwas\s+posted\b.{0,220}?\bon\s+('+DATE+r')(.{0,100})',section))
    filed=date.fromisoformat(filing_date)
    headline=''
    if exhibit is not None:
        release_tree=html.fromstring(exhibit.encode('utf-8') if isinstance(exhibit,str) else exhibit)
        headline=' '.join(_text(release_tree).split())[:1200]
    actual_headline=bool(re.search(r'(?i)\b(?:reports?|announces?)\b.{0,180}\b(?:results|earnings)\b',headline))
    supported=[]
    for m in statements:
        clause=re.split(r'(?<!\b[A-Z]\.)(?<!\bInc\.)(?<!\bCorp\.)(?<!\bLtd\.)(?<=[.!?])\s+(?=[A-Z])',m[2],maxsplit=1)[0]
        # In "announced on DATE, its results", the completed verb precedes the date.
        before_date=m[0][:m.start(1)-m.start()]
        if re.search(r'(?i)\bearnings\s+release\b.*\bwas\s+posted\b',before_date):
            if re.search(r'(?i)preliminary|will|would',before_date):
                continue
            clause='posted results '+before_date
        if re.search(r'(?i)\b(?:announced|reported)\s+on\s*$',before_date):
            clause='reported '+clause
        clause=re.split(r'(?i)\b(?:refer|see)\s+(?:to\s+)?(?:our|the|its|their|a)\b|\b(?:our|the|its|their)\s+(?:(?:previous|prior|earlier)\s+)?(?:Quarterly|Annual)\s+Report\b',clause,maxsplit=1)[0]
        # A completed release and a later call can share one sentence. Require
        # independent actual-results evidence in the dated exhibit before
        # accepting this narrow construction; a call/date announcement is not enough.
        paired_call = re.search(r'(?i)\bissued\s+(?:a|the)\s+(?:press|news)\s+release\s+and\s+will\s+hold\s+a\s+conference\s+call\s+regarding\s+its\s+financial\s+results\b', clause)
        if paired_call and actual_headline and re.search(r'(?i)\btoday\s+(?:reported|announced|released)\b', headline):
            try:
                parse_earnings_release(exhibit, _date(m[1]).isoformat(), filing_date, today)
            except ValueError:
                continue
            supported.append((m, clause))
            continue
        # Evaluate the whole publication clause, including language after its object.
        # A schedule/date/call announcement does not attest release of the actuals.
        if re.search(r'(?i)\bwill\b|\bwould\b|\bschedul\w*|\bupcoming\b|\bforthcoming\b|\bplans?\s+to\b|\bdate\b|\btiming\b|\bconference\b|\bcall\b|\bwebcast\b',clause):continue
        result=re.search(r'(?i)\b(?:reported|announced|released|posted|reporting|announcing|containing|contained|setting\s+forth|relating\s+to|regarding|reports|report)\b(.{0,140}?)\b(?:results(?!\s+(?:conference|call|webcast))|earnings(?=\s+(?:for|of|results)\b|\s*[:$.,;]|\s*$)|sales|net\s+income)\b',clause)
        actual_results=result and not re.search(r'(?i)conference|\bcall\b|webcast|guidance|forecast|\bdate\b|schedul|timing|expect|preliminar',result[1])
        dated_release=bool(re.search(r'(?i)(?:press|news)\s+release.{0,160}\bdated\b',m[0]))
        if actual_results or (dated_release and actual_headline):supported.append((m,clause))
    dates={_date(m[1]) for m,_ in supported}
    if len(dates)!=1:raise ValueError('No unambiguous completed publication date')
    event=dates.pop()
    if not event<=filed<=today or (filed-event).days>45:raise ValueError('Publication date outside the filing window')
    # Exhibit descriptions can explicitly identify a quarter that is not repeated in the body.
    descriptions=re.search(r'(?is)\bItem\s*9\.01\b(.*?)(?=\bSIGNATURES?\b|$)',text)
    publication_text=' '.join(clause for _,clause in supported)
    end=_completed_period_end(publication_text+' '+(descriptions[1] if descriptions else ''),event)
    if end is not None and (event-end).days>180:raise ValueError('Stale earnings period')
    year,quarter=_fiscal_identity(publication_text)
    if exhibit is not None:
        hint=_fiscal_identity(headline)
        if hint[0] is not None:
            if year is not None and (year,quarter)!=hint:raise ValueError('Conflicting official fiscal identities')
            year,quarter=hint
    if end is None and year is None:raise ValueError('No explicit period or fiscal identity')
    return {'date':event.isoformat(),'periodEnd':end.isoformat() if end else None,'fiscalYear':year,'fiscalQuarter':quarter}


def _local(node):
    return str(node.tag).lower().split('}')[-1].split(':')[-1]


def _desc(node, local):
    return [n for n in node.iter() if _local(n) == local]


def _unique_text(nodes):
    values = {' '.join(_text(n).split()) for n in nodes}
    return values.pop() if len(values) == 1 else None


def _contract_revenue_total(node):
    """Contract revenue is a total only on an explicitly labelled consolidated statement row."""
    rows=[n for n in node.iterancestors() if _local(n)=='tr']
    tables=[n for n in node.iterancestors() if _local(n)=='table']
    if not rows or not tables:return False
    cells=rows[0].xpath('./td|./th')
    before=[]
    for cell in cells:
        if node is cell or any(n is node for n in cell.iter()):break
        before.append(_text(cell))
    label=' '.join(' '.join(before).split()).strip(' :$')
    if not re.fullmatch(r'(?i)(?:total )?(?:net )?(?:revenues?|sales(?: to customers)?)(?: \((?:Note )?[a-z0-9]+\))?',label):return False
    table=tables[0]
    statement=r'(?i)(?:(?:(?:consolidated|combined|condensed)\s+)+(?:statements? of (?:income|operations|earnings|comprehensive income)|income statements?)|statements? of (?:(?:consolidated|combined|condensed)\s+)+(?:income|operations|earnings))(?:\s*\(unaudited\))?'
    root=node.getroottree().getroot()
    issuer=_unique_text(n for n in root.iter() if isinstance(n.tag,str) and n.get('name','').lower()=='dei:entityregistrantname')
    def is_statement_heading(text):
        text=' '.join(text.split())
        if issuer:
            text=re.sub(r'(?i)^'+re.escape(issuer)+r'(?:\s+and\s+(?:its\s+)?subsidiaries)?\s+', '', text)
        return bool(re.fullmatch(statement,text))
    forbidden=r'(?i)non.gaap|adjusted|pro[\s-]*forma|reconcil|\bsegment\b|\bnotes?\s+(?:\d+|to\b)'
    first=table.xpath('./caption|./tr|./thead/tr|./tbody/tr')[:8]
    title_rows=[r for r in first if _local(r)=='caption' or len(r.xpath('./td|./th'))==1]
    if any(re.search(forbidden,' '.join(_text(r).split())) for r in title_rows):return False
    if any(is_statement_heading(_text(r)) for r in first):return True
    # SEC HTML often wraps a whole statement table in a separate layout div.
    # Cross only empty single-child wrappers; another table or note is a boundary.
    current=table
    for _ in range(4):
        previous=current.getprevious()
        for _ in range(6):
            if previous is None:break
            heading=' '.join(_text(previous).split())
            if _local(previous)=='table' or previous.xpath('.//table'):return False
            if re.search(forbidden,heading) or re.search(r'(?i)statements? of (?:cash flows|financial position)|balance sheets?',heading):return False
            if is_statement_heading(heading):return True
            previous=previous.getprevious()
        parent=current.getparent()
        if parent is None or _local(parent) not in ('div','section'):break
        # Empty formatting spans beside a table do not change its statement.
        # Any textual sibling or additional table remains a hard boundary.
        siblings = [child for child in parent if child is not current]
        if any(_text(child).strip() or _local(child)=='table' or child.xpath('.//table') for child in siblings):break
        if (parent.text or '').strip() or (current.tail or '').strip():break
        current=parent
    return False


def parse_inline_quarter(document, period_end, cik=None):
    tree = html.fromstring(document.encode('utf-8') if isinstance(document, str) else document)
    nodes = [node for node in tree.iter() if isinstance(node.tag,str)]
    def dei(tag):
        return _unique_text(n for n in nodes if n.get('name', '').lower() == 'dei:' + tag.lower())
    document_ends = set()
    for node in nodes:
        if node.get('name', '').lower() != 'dei:documentperiodenddate':
            continue
        raw_end = ' '.join(_text(node).split())
        try:
            value = _date(raw_end) if re.fullmatch(DATE, raw_end, re.I) else date.fromisoformat(raw_end)
        except ValueError:
            raise ValueError('Official document period does not match release period') from None
        document_ends.add(value.isoformat())
    if document_ends != {period_end}:
        raise ValueError('Official document period does not match release period')
    year, focus = dei('DocumentFiscalYearFocus'), dei('DocumentFiscalPeriodFocus')
    if not year or not year.isdigit() or focus not in ('Q1','Q2','Q3','FY'):
        raise ValueError('Explicit fiscal-year/quarter focus unavailable')
    contexts = {}
    for context in (n for n in nodes if _local(n) == 'context'):
        identifier=_unique_text(_desc(context,'identifier'))
        if cik is not None and (not identifier or not identifier.isdigit() or identifier.lstrip('0')!=str(cik).lstrip('0')):
            continue
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
    noncontract_component=any(n.get('name','').lower()=='us-gaap:revenuenotfromcontractwithcustomer' and n.get('contextref') in contexts for n in nodes)
    eps, revenue, starts = set(), set(), set()
    for node in nodes:
        if _local(node) != 'nonfraction' or node.get('contextref') not in contexts:
            continue
        tag = node.get('name', '')
        is_eps = tag.lower() == 'us-gaap:earningspersharediluted'
        is_revenue = tag.lower() in {t.lower() for t in REVENUE_TAGS}
        # Extension names need an explicit consolidated total row and the same
        # dimensionless quarter context and USD unit as standard facts.
        if (not is_revenue and ':' in tag and tag.split(':')[0].lower() not in ('us-gaap','dei')
                and re.search(r'(?i)revenue|sales', tag.split(':',1)[1])
                and not re.search(r'(?i)adjusted|nongaap|proforma|segment',tag)):
            is_revenue = _contract_revenue_total(node)
        if not is_eps and not is_revenue:
            continue
        if 'revenuefromcontractwithcustomer' in tag.lower() and (noncontract_component or not _contract_revenue_total(node)):
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
