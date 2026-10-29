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
    return ' '.join(tree.itertext()).replace('\xa0', ' ').replace('\u200b', '').replace('\ufeff', '')


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
    identity_text = re.split(r'(?i)all comparisons|compared (?:to|with)|forward-looking|forecasting|\boutlook\b|\bguidance\s+(?:for|:)',intro)[0]
    patterns = [
        r'(?i)\b(first|second|third|fourth|1st|2nd|3rd|4th)[\s-]+quarter[\s-]+(?:and[\s-]+(?:(?:full[\s-]+)?(?:fiscal[\s-]+)?year[\s-]+|fiscal[\s-]+))?(?:of[\s-]+)?(?:fiscal[\s-]+)?(?:year[\s-]+)?(20\d{2})\b',
        r'(?i)\bQ([1-4])\s+(?:FY\s*)?(20\d{2})\b',
        r'(?i)\b(20\d{2})[\s-]+(first|second|third|fourth)[\s-]+quarter\b',
    ]
    def not_comparison(m):
        prefix=identity_text[max(0,m.start()-40):m.start()]
        suffix=intro[m.end():m.end()+40]
        return (not re.search(r'(?i)\b(?:versus|vs\.?)\s*$',prefix)
                and not re.match(r'(?i)\s+(?:(?:acquisition\s+)?closing|guidance|outlook|forecast|projections?|targets?)\b',suffix))
    matches=[(m.start(),int(m[2]),int(m[1]) if m[1].isdigit() else QUARTERS[m[1].lower()]) for p in patterns[:2] for m in re.finditer(p,identity_text) if not_comparison(m)]
    def not_publication_date(m):
        prefix=identity_text[max(0,m.start()-40):m.start()+len(m[1])]
        return not re.search(DATE+r'\s*$',prefix,re.I)
    matches += [(m.start(),int(m[1]),QUARTERS[m[2].lower()]) for m in re.finditer(patterns[2],identity_text) if not_publication_date(m) and not_comparison(m)]
    matches += [(m.start(),int(m[1]),QUARTERS[m[2].lower()]) for m in re.finditer(
        r'(?i)\b(?:fiscal\s+)?(20\d{2})\s+(?:(?:full[-\s]?year)\s+and\s+)?(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\b',
        identity_text) if not_publication_date(m) and not_comparison(m)]
    matches += [(m.start(),int('20'+m[2]) if len(m[2])==2 else int(m[2]),int(m[1])) for m in re.finditer(r'(?i)\b([1-4])Q\s*(20\d{2}|\d{2})\b',identity_text) if not_comparison(m)]
    return min(matches)[1:] if matches else (None,None)


def _completed_period_end(text, event):
    text=re.sub(r'(?i)\bthree[ -]month\s+period\b','three months',text)
    periods = [m[1] for m in re.finditer(r'(?i)(?:quarter(?:\s+and\s+(?:(?:full\s+)?(?:fiscal\s+)?year|(?:six|nine)\s+months))?|three(?:\s+and\s+(?:six|nine))?\s+months)\s+(?:ended|ending)\s+(' + DATE + ')', text)]
    periods += [m[1] for m in re.finditer(r'(?i)quarter\s+(?:of\s+)?(?:fiscal\s+)?(?:year\s+)?20\d{2},?\s+which\s+ended\s+(?:on\s+)?('+DATE+')',text[:3000])]
    ends = {_date(p) for p in periods if _date(p) < event}
    return max(ends) if ends else None


def _preliminary_results(text):
    intro=text[:3000]
    historical_modifier=r'(?i)\b(?:previously\s+(?:reported|announced|released)|(?:prior|earlier|previous)(?:\s+reported)?|compared\s+(?:to|with)(?:\s+the)?)\s*$'
    for match in re.finditer(r'(?i)\bpreliminar\w*\b.{0,160}?\b(?:results|earnings)\b',intro):
        prefix=intro[max(0,match.start()-75):match.start()]
        historical=re.search(historical_modifier,prefix)
        if not historical:
            return True
    for match in re.finditer(r'(?i)\b(?:results|earnings)\b([^.!?;\n]{0,160}?)\bpreliminar\w*\b',intro):
        gap=match[1]
        prefix=intro[max(0,match.start()-75):match.start()]+match[0][:match.start(1)-match.start()]+gap
        predicate=re.search(r'(?i)\b(?:are|were|is|remain|remains|(?:reported|presented|shown|considered) as)\s*$',gap)
        if (predicate or not gap.strip(' \t,:()—-')) and not re.search(historical_modifier,prefix):
            return True
    return False


def non_actual_release_reason(document):
    """Positive original-text counterevidence, never a parse-failure heuristic."""
    tree=html.fromstring(document.encode('utf-8') if isinstance(document,str) else document)
    for node in tree.xpath('//script|//style'):
        node.drop_tree()
    intro=' '.join(_text(tree).split())[:3000]
    if (re.search(r'(?i)\bsubject to finalization of the financial reporting process\b',intro)
            and re.search(r'(?i)\bthis information is intended only to provide additional information regarding current estimates\b',intro)):
        return 'unfinalized_quarter_estimates'
    if (re.search(r"(?i)\bannounced today updates to management['’]s current financial outlook\b",intro)
            and not list(_current_results_claims(intro))):
        return 'outlook_update_not_quarter_results'
    return None


def _current_results_claims(intro):
    for match in re.finditer(r'(?i)\btoday\s+(?:announced|reported|released)\b[^.!?;]{0,300}',intro):
        clause=match[0]
        prefix=intro[max(0,match.start()-60):match.start()]
        prefix=re.split(r'(?<=[.!?;])\s+',prefix)[-1]
        if re.search(r'(?i)\b(?:previously|earlier|prior|compared\s+(?:to|with)|versus)\b',prefix):continue
        if re.search(r'(?i)\b(?:guidance|outlook|forecast|expected|projected|target|plans)\b',clause):continue
        if re.search(r'(?i)\b(?:results|earnings)\b',clause):yield clause


def _announced_result_identity(intro):
    # A forecast headline can precede the actual results paragraph. Only a
    # completed, current announcement with its own explicit identity can
    # recover what the ordinary comparison/guidance boundary omitted.
    claims=set()
    for clause in _current_results_claims(intro):
        identity=_fiscal_identity(clause)
        if identity[0] is not None:claims.add(identity)
    return next(iter(claims)) if len(claims)==1 else (None,None)


def parse_earnings_release(document, event_date, filing_date, today):
    if non_actual_release_reason(document):
        raise ValueError('Original document explicitly describes estimates or an outlook update')
    tree = html.fromstring(document.encode('utf-8') if isinstance(document, str) else document)
    for node in tree.xpath('//script|//style'):
        node.drop_tree()
    text = ' '.join(_text(tree).split())
    intro = text[:3000]
    if _preliminary_results(intro):
        raise ValueError('Preliminary results do not confirm the completed earnings release')
    if not re.search(r'(?i)\b(?:results|earnings)\b', intro):
        raise ValueError('Not an earnings release')
    event, filed = date.fromisoformat(event_date), date.fromisoformat(filing_date)
    # The SEC event date is merely a candidate; original exhibit must explicitly confirm it.
    intro_dates = {_date(m[0]) for m in re.finditer(DATE, intro, re.I)}
    if event not in intro_dates or not event <= filed <= today:
        raise ValueError('Original earnings exhibit does not confirm release date')
    # A later note can refer to a different quarter (for example an acquisition
    # financing comparison). Only the introduction describes this release;
    # exact statement headers and matching filings provide remaining evidence.
    end = _completed_period_end(intro,event)
    year,fiscal_quarter=_fiscal_identity(intro)
    if year is None:
        year,fiscal_quarter=_announced_result_identity(intro)
    statement_period=None
    if end is None and year is not None:
        from official_metrics import discover_statement_period
        statement_period=discover_statement_period(document,event.isoformat(),year,fiscal_quarter)
        if statement_period:end=date.fromisoformat(statement_period['periodEnd'])
    if end is None and year is None:
        raise ValueError('No explicit completed quarterly period or fiscal identity')
    if end is not None and (event - end).days > 180:
        raise ValueError('Release period is not current for this event')
    # Prefer the earliest current headline identity, including joint Q4/FY headlines.
    # Later comparative paragraphs cannot provide the quarter's fiscal year.
    result={'date': event.isoformat(), 'periodEnd': end.isoformat() if end else None,
            'fiscalYear':year, 'fiscalQuarter':fiscal_quarter}
    if statement_period:result['periodEndEvidence']={'locator':statement_period['locator']}
    return result


def parse_earnings_filing(document,event_date,filing_date,today,exhibit=None):
    """An explicit Item 2.02 publication statement is release evidence, not its cover date."""
    if non_actual_release_reason(document):
        raise ValueError('Original filing explicitly describes estimates or an outlook update')
    tree=html.fromstring(document.encode('utf-8') if isinstance(document,str) else document)
    # Keep block boundaries so a nearby footnote cannot become part of a publication.
    for node in tree.iter():
        if _local(node) in ('p','div','tr','h1','h2','h3','h4'):
            node.tail=(node.tail or '')+'\n'
    text='\n'.join(' '.join(line.split()) for line in _text(tree).splitlines() if line.strip())
    match=re.search(r'(?is)\bItem\s*2\.02\b(.*?)(?=\bItem\s*(?!(?:2\.02|7\.01)\b)\d+\.\d+\b|\bSIGNATURES?\b|$)',text)
    if not match:raise ValueError('No earnings publication statement')
    section=match[1]
    # SEC layout sometimes wraps the issuer and completed publication verb
    # across lines within the same sentence; do not join completed sentences.
    section=re.sub(r'(?im)(\bOn\s+(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?'+DATE+r'[^\n]{0,220}(?<![.!?]))\n(?=(?:issued|announced|reported|released|posted)\b)',r'\1 ',section)
    statements=list(re.finditer(r'(?i)\bOn\s+(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?('+DATE+r')\s*,?\s+(.{0,350}?(?:reported|announced|issued|released|posted)\b.{0,250})',section))
    statements += list(re.finditer(r'(?i)\b(?:announced|reported)\s+on\s+('+DATE+r')(.{0,400})',section))
    statements += list(re.finditer(r'(?i)(?:press|news)\s+release(?:(?!'+DATE+r').){0,150}?(?:dated|issued(?:\s+by.{0,100}?)?\s+on)\s+('+DATE+r')(.{0,400})',section))
    statements += list(re.finditer(r'(?i)('+DATE+r')\s+press\s+release(.{0,400})',section))
    filed=date.fromisoformat(filing_date)
    headline=''
    if exhibit is not None:
        if non_actual_release_reason(exhibit):
            raise ValueError('Linked exhibit explicitly describes estimates or an outlook update')
        release_tree=html.fromstring(exhibit.encode('utf-8') if isinstance(exhibit,str) else exhibit)
        exhibit_intro=' '.join(_text(release_tree).split())[:3000]
        headline=exhibit_intro[:1200]
        if _preliminary_results(exhibit_intro):
            raise ValueError('Preliminary exhibit does not confirm completed earnings')
    actual_headline=bool(re.search(r'(?i)\b(?:reports?|announces?)\b.{0,180}\b(?:results|earnings)\b',headline))
    supported=[]
    for m in statements:
        # Corporate abbreviations inside a release title are not sentence boundaries.
        clause=re.split(r'(?<!Inc\.)(?<!Corp\.)(?<!Co\.)(?<!Ltd\.)(?<=[.!?])\s+(?=[A-Z])',m[2],maxsplit=1)[0]
        # In "announced on DATE, its results", the completed verb precedes the date.
        before_date=m[0][:m.start(1)-m.start()]
        if re.search(r'(?i)\b(?:announced|reported)\s+on\s*$',before_date):
            clause='reported '+clause
        clause=re.split(r'(?i)\b(?:refer|see)\s+(?:to\s+)?(?:our|the|its|their|a)\b|\b(?:our|the|its|their)\s+(?:(?:previous|prior|earlier)\s+)?(?:Quarterly|Annual)\s+Report\b',clause,maxsplit=1)[0]
        # Evaluate the whole publication clause, including language after its object.
        # A schedule/date/call announcement does not attest release of the actuals.
        if re.search(r'(?i)\bwill\b|\bwould\b|\bschedul\w*|\bupcoming\b|\bforthcoming\b|\bplans?\s+to\b|\bdate\b|\btiming\b|\bconference\b|\bcall\b|\bwebcast\b|\bpreliminar\w*\b',clause):continue
        result=re.search(r'(?i)\b(?:reported|announced|released|posted|reporting|announcing|containing|regarding|reports?|announces?)\b(.{0,140}?)\b(?:results(?!\s+(?:conference|call|webcast))|earnings(?=\s+(?:for|of|results|and)\b|\s*[:$.,;]|\s*$)|sales|net\s+income)\b',clause)
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
    exhibit_index = re.split(r'(?i)\b(?:cautionary statement|forward[- ]looking statements|risk factors)\b',
                             descriptions[1] if descriptions else '', maxsplit=1)[0]
    end=_completed_period_end(publication_text+' '+exhibit_index,event)
    exhibit_end=_completed_period_end(headline,event) if actual_headline else None
    if end is not None and exhibit_end is not None and end != exhibit_end:
        raise ValueError('Conflicting official quarterly periods')
    end=end or exhibit_end
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


def _statement_scope(text):
    normalized=' '.join(text.split())
    result=r'(?:(?:net |comprehensive )?income|operations|earnings)'
    statement=rf'statements? of {result}'
    title=rf'(?:(?:consolidated|combined)(?: condensed)? (?:{statement}|(?:net )?income statements?)|statements? of (?:consolidated|combined) {result})'
    if re.search(r'(?i)\bpro[ -]?forma\b.{0,180}\b'+title+r'|\b'+title+r'.{0,150}\b(?:pro[ -]?forma|reflecting\b.{0,100}\bas discontinued operations)\b',normalized):
        return 'recast'
    if re.search(r'(?i)\b(?:joint[ -]ventures?|unconsolidated|segments?)\b.{0,80}\b(?:'+title+'|'+statement+')',normalized):
        return 'nonconsolidated'
    if re.search(r'(?i)\b'+title,normalized):
        return 'consolidated'
    return None


def _contract_revenue_total(node):
    """Contract revenue is a total only on an explicitly labelled consolidated statement row."""
    rows=[n for n in node.iterancestors() if _local(n)=='tr']
    tables=[n for n in node.iterancestors() if _local(n)=='table']
    if not rows or not tables:return False
    cells=rows[0].xpath('./td|./th')
    before=[]
    for cell in cells:
        if node is cell or any(n is node for n in cell.iter()):break
        content=' '.join(_text(cell).split())
        # Labels precede the first amount, including when the current year is
        # to the right of a comparative amount in the same statement row.
        if re.fullmatch(r'[$(\d,.)\s%-]+',content):break
        before.append(content)
    label=' '.join(' '.join(before).split()).strip(' :$')
    label=re.sub(r'(?i)\s*\(notes?\s+\d+(?:\s*(?:,|and)\s*\d+)*\)\s*$','',label).strip()
    if not re.fullmatch(r'(?i)(?:total )?(?:net )?(?:revenues?|sales)(?: \([a-z0-9]+\))?',label):return False
    table=tables[0]
    scope=_statement_scope(' '.join(_text(table).split())[:700])
    if scope is not None:return scope == 'consolidated'
    # Use the same bounded heading traversal as the exact-period table reader.
    # Empty anchors and layout wrappers do not erase an explicit nearby title.
    from official_metrics import _context
    return _statement_scope(_context(table)) == 'consolidated'


def _gross_revenue_line(node):
    """Identify an explicitly labelled gross line when a separate net total exists."""
    row=next((n for n in node.iterancestors() if _local(n)=='tr'),None)
    if row is None:return False
    prior=[]
    for cell in row.xpath('./td|./th'):
        if node is cell or any(n is node for n in cell.iter()):break
        content=' '.join(_text(cell).split())
        if re.fullmatch(r'[$(\d,.)\s%-]+',content):break
        prior.append(content)
    label=' '.join(' '.join(prior).split()).strip(' :$')
    return bool(re.fullmatch(r'(?i)(?:total )?gross revenues?',label))


def _document_period_end(nodes):
    """Normalize equivalent explicit DEI dates before testing their uniqueness.

    Numeric dates require the declared month/day/year transform. Supporting
    this bounded subset never guesses the order of an untagged numeric date.
    """
    dates = set()
    for node in nodes:
        if node.get('name', '').lower() != 'dei:documentperiodenddate':
            continue
        raw = ' '.join(_text(node).split())
        transform = node.get('format', '').split(':')[-1]
        try:
            if transform in ('date-month-day-year', 'datemonthdayyear'):
                parts = re.fullmatch(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})', raw)
                if not parts:
                    return None
                value = date(int(parts[3]), int(parts[1]), int(parts[2]))
            elif transform in ('', 'date-monthname-day-year-en', 'datemonthdayyearen',
                               'date-day-monthname-year-en', 'datedaymonthyearen'):
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw) and not transform:
                    value = date.fromisoformat(raw)
                elif re.fullmatch(DATE, raw, re.I):
                    value = _date(raw)
                else:
                    return None
            else:
                return None
            dates.add(value.isoformat())
        except ValueError:
            return None
    return next(iter(dates)) if len(dates) == 1 else None


def parse_inline_quarter(document, period_end, cik=None):
    tree = html.fromstring(document.encode('utf-8') if isinstance(document, str) else document)
    nodes = [node for node in tree.iter() if isinstance(node.tag,str)]
    def dei(tag):
        return _unique_text(n for n in nodes if n.get('name', '').lower() == 'dei:' + tag.lower())
    document_end = _document_period_end(nodes)
    if document_end != period_end:
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
    unit_currencies = {}
    for unit in (n for n in nodes if _local(n) == 'unit'):
        monetary_currencies = set()
        for measure in _desc(unit,'measure'):
            currency_match=re.fullmatch(r'(?i)iso4217:([A-Z]{3})',_text(measure).strip())
            if currency_match:monetary_currencies.add(currency_match[1].lower())
        if len(monetary_currencies)==1:unit_currencies[unit.get('id')]=next(iter(monetary_currencies))
        numerator = _desc(unit, 'unitnumerator')
        denominator = _desc(unit, 'unitdenominator')
        if numerator and denominator:
            if (_unique_text(_desc(numerator[0], 'measure')) or '').lower() == 'iso4217:usd' and (_unique_text(_desc(denominator[0], 'measure')) or '').lower() == 'xbrli:shares':
                units[unit.get('id')] = 'USD/shares'
        elif (_unique_text(_desc(unit, 'measure')) or '').lower() == 'iso4217:usd':
            units[unit.get('id')] = 'USD'
    noncontract_component=any(n.get('name','').lower()=='us-gaap:revenuenotfromcontractwithcustomer' and n.get('contextref') in contexts for n in nodes)
    eps, revenue, gross_revenue, starts, net_interest_revenue = set(), set(), set(), set(), set()
    for node in nodes:
        if _local(node) != 'nonfraction' or node.get('contextref') not in contexts:
            continue
        tag = node.get('name', '')
        is_eps = tag.lower() == 'us-gaap:earningspersharediluted'
        is_revenue = tag.lower() in {t.lower() for t in REVENUE_TAGS}
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
        (eps if is_eps else gross_revenue if _gross_revenue_line(node) else revenue).add(float(value))
        if tag.lower() == 'us-gaap:revenuesnetofinterestexpense':net_interest_revenue.add(float(value))
        starts.add(contexts[node.get('contextref')])
    # A tagged gross line cannot stand in for a separately reported contract
    # revenue total. Leave the filing field open for the release statement.
    competing_total=any(_local(node)=='nonfraction' and node.get('contextref') in contexts
                        and node.get('name','').lower()=='us-gaap:revenuefromcontractwithcustomerexcludingassessedtax'
                        for node in nodes)
    if not revenue and not competing_total:
        revenue = gross_revenue
    result = {'fiscalYear':int(year), 'fiscalQuarter':4 if focus == 'FY' else int(focus[-1]),
            'periodScope':'quarter', 'periodEnd':period_end,
            'periodStart': next(iter(starts)) if len(starts)==1 else None,
            'epsGaapDiluted':next(iter(eps)) if len(eps)==1 else None,
            'revenue':next(iter(revenue)) if len(revenue)==1 and not (gross_revenue and competing_total) else None,
            'epsBasis':'GAAP diluted', 'currency':'USD'}
    if contexts and (not eps or not revenue or (len(revenue)>1 and len(net_interest_revenue)==1)):
        # The document identity and quarter are already explicit. Some issuers
        # use different XBRL concepts for a clearly labelled total diluted EPS;
        # use the same exact-period consolidated statement reader as releases.
        from official_metrics import parse_statement_metrics, _net_revenue_total, _grid
        statement = parse_statement_metrics(document, period_end, currency='USD',
            fiscal_year=result['fiscalYear'], fiscal_quarter=result['fiscalQuarter'])
        tables=tree.xpath('//table')
        def selected_cell_validation(field, locator, value):
            try:
                table=tables[locator['table']-1]
                cell=_grid(table,include_nodes=True)[locator['row']-1][locator['column']-1]
            except (KeyError,IndexError,TypeError):return None
            if cell is None:return None
            facts=[n for n in cell.iter() if _local(n) in ('nonfraction','nonnumeric','fraction')]
            if facts:
                for fact in facts:
                    if (_local(fact) != 'nonfraction' or fact.get('contextref') not in contexts
                            or units.get(fact.get('unitref')) != ('USD/shares' if field=='epsGaapDiluted' else 'USD')
                            or fact.get('format','').split(':')[-1] not in ('','num-dot-decimal','numdotdecimal')
                            or fact.get('sign') not in (None,'-')):return None
                    raw=''.join(_text(fact).split()).replace(',','')
                    if not re.fullmatch(r'\d+(?:\.\d+)?',raw):return None
                    try:
                        scale=int(fact.get('scale','0'))
                        if not -12<=scale<=15:return None
                        actual=Decimal(raw)*Decimal(10)**scale*(-1 if fact.get('sign')=='-' else 1)
                        precision=Decimal(str(locator.get('precision','0')))
                        if (not actual.is_finite() or not precision.is_finite() or precision<0
                                or abs(actual-Decimal(str(value)))>precision/2):return None
                    except (ValueError,InvalidOperation):return None
                return 'selected_inline_fact'
            currencies={unit_currencies[n.get('unitref')] for n in table.iter()
                if n.get('contextref') in contexts and n.get('unitref') in unit_currencies}
            return 'untagged_quarter_statement' if currencies=={'usd'} else None
        if len(revenue)>1 and len(net_interest_revenue)==1:
            net_value=next(iter(net_interest_revenue))
            locator=statement.get('metricLocators',{}).get('revenue',{})
            validation=selected_cell_validation('revenue',locator,net_value) if locator else None
            if statement.get('revenue') == net_value and _net_revenue_total(locator.get('label','')) and validation:
                locator={**locator,'validationBasis':validation}
                result['revenue']=net_value
                result.setdefault('metricLocators',{})['revenue']=locator
                result['metricDefinitionEvidence']={'revenue':{
                    'definition':'consolidated_revenue_net_of_interest_expense',
                    'selectedTag':'RevenuesNetOfInterestExpense','selectedValue':net_value,
                    'statementLocator':locator,'otherTaggedValues':sorted(revenue-{net_value})}}
        for field, values in [('epsGaapDiluted',eps),('revenue',revenue)]:
            ambiguous_gross = field == 'revenue' and gross_revenue and competing_total
            if not values and not ambiguous_gross and statement.get(field) is not None:
                locator=statement['metricLocators'][field]
                validation=selected_cell_validation(field,locator,statement[field])
                if not validation:continue
                result[field]=statement[field]
                result.setdefault('metricLocators',{})[field]={**locator,'validationBasis':validation}
    return result
