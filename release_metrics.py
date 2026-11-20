"""Explicit quarterly GAAP statement columns for reviewed USD issuer layouts.

Read only reviewed issuer layouts and explicitly labelled quarterly amounts.
Q4 is read directly from the statement's three-month column.
"""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from lxml import html

SUPPORTED_ISSUERS = {'0000789019', '0001326801', '0000310764',
                     '0000320193', '0000002488', '0001018724', '0001596532', '0000001800',
                     '0000002969', '0000882184', '0001013237', '0000857005', '0000804328',
                     '0001341439', '0000720005', '0001045810', '0000354950',
                     '0001744489', '0000027419', '0000060667', '0000109198',
                     '0001327567', '0001474432', '0001601046', '0000745732',
                     '0000104169', '0000719955'}

REVENUE_MILLION_UNITS = {
    '0000310764': r'\bmillions of dollars\b',
    '0000002488': r'\bmillions\b',
    '0000002969': r'\bmillions of u\.s\. dollars\b',
    '0000027419': r'\bmillions\b',
}

def _text(node):
    if not isinstance(node.tag, str):
        return ''
    return ' '.join(' '.join(node.itertext()).split())

def _grid(table):
    """Expand HTML header spans so quarter/year headings retain their columns."""
    occupied = {}
    output = []
    rows = table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr')
    for y, row in enumerate(rows[:1000]):
        x = 0
        for cell in row.xpath('./td|./th'):
            if 'display:none' in cell.get('style', '').replace(' ', '').lower():
                continue
            while (y, x) in occupied:
                x += 1
            width, height = int(cell.get('colspan', '1')), int(cell.get('rowspan', '1'))
            if not (1 <= width <= 128 and 1 <= height <= 1000 and x + width <= 128):
                raise ValueError('Unsupported statement span')
            value = _text(cell)
            for dy in range(height):
                for dx in range(width):
                    occupied[y+dy, x+dx] = value
            x += width
        length = max((col+1 for rownum,col in occupied if rownum == y), default=0)
        output.append([occupied.get((y, col), '') for col in range(length)])
    return output

def _scope(table, cik=None):
    """Use a nearby income-statement heading, bounded by notes and other tables."""
    prefix = []
    # Some original exhibits put the statement title in a full-width table row.
    # Use an exact title before the data, never a loose mention in a note.
    first_rows = table.xpath('./tr|./thead/tr|./tbody/tr')[:8]
    title_pattern = r'(?i)(?:unaudited\s+)?(?:(?:condensed|consolidated|combined)\s+)*(?:statements? of (?:income|operations|earnings)|income statements?)(?:\s*\(Unaudited\))?'
    header_text = ' '.join(_text(row) for row in first_rows)
    for row in first_rows:
        labels = [label for cell in row.xpath('./td|./th') if (label := _text(cell))]
        if cik == '0001327567':
            labels = [re.sub(r'(?i)^preliminary\s+', '', label) for label in labels]
        if len(labels)==1 and re.fullmatch(title_pattern, labels[0]):
            if re.search(r'(?i)non.gaap|adjusted|comprehensive|segment|notes?\s+(?:\d+|to\b)', header_text):
                return None
            return header_text
    caption = table.find('caption')
    if caption is not None:
        prefix.append(_text(caption))
    current = table
    for _ in range(4):
        previous = current.getprevious()
        for _ in range(12):
            if previous is None:
                break
            text = _text(previous)
            if (cik == '0000104169' and current is table and previous is table.getprevious()
                    and previous.tag == 'table'
                    and re.fullmatch(r'(?i)Walmart Inc\. Condensed Consolidated Statements of Income\s*\(Unaudited\)', text)):
                return text
            if previous.tag == 'table' or previous.xpath('.//table'):
                return None
            prefix.append(text)
            if re.search(r'(?i)non.gaap|adjusted|comprehensive|segment|notes?\s+(?:\d+|to\b)|balance sheet|cash flow', text):
                return None
            if re.fullmatch(title_pattern, text):
                return ' '.join(prefix)
            if cik == '0000060667' and re.fullmatch(r'(?i)Consolidated Statements of Current Earnings and Accumulated Deficit \(Unaudited\)', text):
                return ' '.join(prefix)
            if (cik == '0000109198'
                    and text.casefold() == 'the tjx companies, inc. and consolidated subsidiaries'
                    and {label.casefold() for label in prefix} >= {'financial summary', '(unaudited)'}):
                return ' '.join(prefix)
            previous = previous.getprevious()
        parent = current.getparent()
        if parent is None or parent.tag not in ('div','section'):
            break
        if (parent.text or '').strip() or (current.tail or '').strip():
            break
        if any(_text(child) or child.tag=='table' or child.xpath('.//table') for child in parent if child is not current):
            break
        current = parent
    # Captions must also be explicit GAAP income-statement titles.
    if caption is not None and re.fullmatch(r'(?i)(?:(?:condensed|consolidated|combined)\s+)*(?:statements? of (?:income|operations|earnings)|income statements?)(?:\s*\(Unaudited\))?', _text(caption)):
        return ' '.join(prefix)
    return None

def _number(raw):
    raw = re.sub(r'\s+', '', raw).replace(',', '').replace('$','')
    negative = raw.startswith('(') and raw.endswith(')')
    if negative:
        raw = raw[1:-1]
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', raw):
        return None
    try:
        value = Decimal(raw)
        if negative:
            value = -value
        return value if value.is_finite() else None
    except InvalidOperation:
        return None

def _stryker_columns(headers, end):
    """Stryker shares month/day above separate duration and year columns."""
    shared = {row[0] for row in headers if row and row[0] and len(set(row)) == 1}
    period = r'For the Three(?: and (?:Six|Nine))? Months ' + end.strftime('%B') + ' ' + str(end.day)
    dates = {text for text in shared if re.search(r'(?i)\bmonths\b', text)}
    if (len(dates) != 1 or not re.fullmatch(period, next(iter(dates)), re.I)
            or any(re.fullmatch(r'20\d{2}', text) for text in shared)):
        return []
    columns = []
    for x in range(1, max(map(len, headers), default=0)):
        # The common title lists all durations; only the column's own duration
        # and year may choose a quarter. Percent-change columns have no year.
        parts = [row[x] for row in headers if x < len(row) and row[x] and row[x] not in shared]
        years = {p for p in parts if re.fullmatch(r'20\d{2}', p)}
        if ('Three Months' in parts and years == {str(end.year)}
                and not any(re.search(r'(?i)six|nine|twelve|year|%|change', p) for p in parts)):
            columns.append(x)
    return columns


def _tesla_update_metrics(tree, end):
    """Read the reviewed SEC image-exhibit's embedded statement-slide text.

    The incoming period is independently verified by the official filing.
    Calendar-quarter labels bind columns only for Tesla's reviewed calendar;
    this does not establish fiscal identity or apply to other issuers.
    """
    quarter = {(3,31):1, (6,30):2, (9,30):3, (12,31):4}.get((end.month,end.day))
    if quarter is None:
        return {}
    wanted = f'Q{quarter}-{end.year}'
    values = {'revenue': set(), 'epsGaapDiluted': set()}
    units = 'In millions of USD or shares as applicable, except per share data '
    for node in tree.xpath('//font[not(*)]'):
        text = _text(node)
        compact = re.sub(r'\s+', '', text)
        if (not text.startswith(units) or 'STATEMENTOFOPERATIONS(Unaudited)' not in compact
                or any(word in compact.lower() for word in ('non-gaap','non–gaap','adjusted','segment','comprehensive'))):
            continue
        header, separator, _ = text.partition(' REVENUES ')
        columns = header[len(units):].split()
        if (not separator or not 1 <= len(columns) <= 8 or len(set(columns)) != len(columns)
                or not all(re.fullmatch(r'Q[1-4]-20\d{2}', col) for col in columns)
                or wanted not in columns):
            continue
        x = columns.index(wanted)
        revenue = re.search(r'\bTotal revenues\s+(.*?)\s+COST OF REVENUES\b', text)
        eps = re.search(r'Net income per share of common stock attributable to common stockholders\s+'
                        r'Basic(?:\s+\(\d+\))?\s+.*?\s+Diluted(?:\s+\(\d+\))?\s+'
                        r'(.*?)\s+Weighted average shares\b', text)
        for metric, match in (('revenue', revenue), ('epsGaapDiluted', eps)):
            if match is None:
                continue
            tokens = match[1].replace('$','').split()
            parsed = [_number(token) for token in tokens]
            if len(parsed) != len(columns) or any(value is None for value in parsed):
                continue
            value = parsed[x]
            if metric == 'revenue' and value < 0:
                continue
            values[metric].add(float(value * 1000000 if metric == 'revenue' else value))
    return {key: next(iter(found)) for key,found in values.items() if len(found)==1}


def _raymond_james_supplement_metrics(tree, end):
    # In this SEC image exhibit the issuer supplies searchable statement text.
    title = 'RAYMOND JAMES FINANCIAL, INC. Consolidated Statements of Income (Unaudited)'
    prefix = 'Three months ended % change from Twelve months ended in millions, except per share amounts '
    values = {'revenue': set(), 'epsGaapDiluted': set()}
    for node in tree.xpath('//font[not(*)]'):
        text = _text(node)
        if not text.startswith(prefix) or title not in text:
            continue
        header, separator, statement = text[len(prefix):].partition(' Revenues:')
        dates = re.findall(r'[A-Z][a-z]+ \d{1,2}, 20\d{2}', header)
        if not separator or len(dates) != 9:
            continue
        try:
            quarters = [datetime.strptime(day, '%B %d, %Y').date() for day in dates[:5]]
        except ValueError:
            continue
        if sorted(set(quarters)) != quarters or end not in quarters:
            continue
        rows = {
            'revenue': re.search(r'\bTotal revenues (.*?) Interest expense\b', statement),
            'epsGaapDiluted': re.search(r'\bEarnings per common share [–-] diluted \(2\) (.*?) Weighted-average common shares', statement),
        }
        for field, match in rows.items():
            if match is None:
                continue
            cells = match[1].replace('$', '').replace('%', '').split()
            amounts = [_number(cell) for cell in cells]
            if len(amounts) != 10 or any(amount is None for amount in amounts):
                continue
            value = amounts[quarters.index(end)]
            if field == 'revenue' and value < 0:
                continue
            values[field].add(float(value * 1000000 if field == 'revenue' else value))
    return {key: next(iter(found)) for key, found in values.items() if len(found)==1}


def parse_release_quarter_metrics(document, period_end, cik):
    """Return only unambiguous directly reported quarterly totals and diluted EPS."""
    cik = str(cik).zfill(10)
    if cik not in SUPPORTED_ISSUERS and cik != '0001318605':
        return {}
    end = date.fromisoformat(period_end)
    if isinstance(document, str):
        tree = html.fromstring(document.encode('utf-8'), parser=html.HTMLParser(encoding='utf-8'))
    else:
        tree = html.fromstring(document)
    if cik == '0001318605':
        return _tesla_update_metrics(tree, end)
    if cik == '0000720005':
        return _raymond_james_supplement_metrics(tree, end)
    everpure_period = None
    if cik == '0001474432':
        # The statement columns print fiscal quarter and year rather than dates.
        # Require a dated quarter narrative tying those labels to this period.
        narrative = _text(tree)[:2500]
        month = end.strftime('%B')
        matched = re.search(r'(?i)\b(first|second|third|fourth) quarter (?:of )?fiscal year '
                            rf'(20\d{{2}}) ended {month} {end.day},\s*{end.year}\b', narrative)
        if not matched:
            return {}
        everpure_period = f'{matched[1]} quarter of fiscal {matched[2]}'.casefold()
    revenue_heading = r'(?i)(?:total\s+)?(?:net\s+)?(?:revenues?|sales)\s*:?'
    revenue_label = r'(?i)total revenues?' if cik == '0000104169' else revenue_heading
    diluted_eps_label = {
        '0000002969': 'diluted earnings (loss) per share attributable to air products',
        '0001327567': 'net income per share, diluted',
        '0001474432': 'net income per share attributable to common stockholders, diluted',
        '0000104169': 'diluted net income per common share attributable to walmart',
    }.get(cik)
    values = {'revenue': set(), 'epsGaapDiluted': set()}
    for table in tree.xpath('//table'):
        if table.xpath('.//table'):
            continue
        scope = _scope(table, cik)
        if scope is None and cik == '0000060667':
            # Lowe's puts its issuer name, exact GAAP title and units in one row.
            first = table.xpath('./tr|./thead/tr|./tbody/tr')[:1]
            title = _text(first[0]) if first else ''
            if re.fullmatch(r"Lowe's Companies, Inc\. Consolidated Statements of Current Earnings and Accumulated Deficit \(Unaudited\) In Millions, Except Per Share and Percentage Data", title):
                scope = title
        if scope is None:
            continue
        try:
            grid = _grid(table)
        except (ValueError, TypeError):
            continue
        labels = [re.sub(r'\s*\(\d+\)$', '', next((value for value in row if value and not re.fullmatch(r'\d+\)|\(\d+\)',value)), '')) for row in grid]
        boundary = next((i for i,label in enumerate(labels) if re.fullmatch(revenue_heading,label)), None)
        if boundary is None:
            continue
        headers = grid[:boundary]
        units = scope+' '+' '.join(' '.join(row) for row in headers)
        if re.search(r'(?i)\beuros?\b|\b(?:EUR|GBP|CAD|AUD|JPY|CNY)\b', units):
            continue
        scale = 1000000
        thousands = (cik in ('0001013237', '0000857005', '0001474432', '0000719955')
                     and re.search(r'\bin thousands\b', units, re.I))
        if thousands or (cik == '0000745732' and '($000, except stores and per share data' in units):
            if re.search(r'\bin millions\b', units, re.I):
                continue
            scale = 1000
        elif not re.search(REVENUE_MILLION_UNITS.get(cik, r'\bin millions\b'), units, re.I):
            continue
        width = max(map(len,grid), default=0)
        columns = []
        for x in range(1,width):
            if cik == '0000060667' and not any(x < len(row) and row[x] == 'Amount' for row in headers):
                continue
            header = ' '.join(dict.fromkeys(row[x] for row in headers if x < len(row) and row[x]))
            if everpure_period:
                if header.casefold() == everpure_period:
                    columns.append(x)
                continue
            if cik in ('0000104169', '0000719955') and re.search(r'(?i)%|percent change', header):
                continue
            duration = r'(?i)\b(?:three months|quarter) ended\b' if cik == '0001744489' else r'(?i)\bthree months ended\b'
            if cik in ('0000109198', '0000719955'):
                duration = r'(?i)\bthirteen weeks ended\b'
            if not re.search(duration,header) or re.search(r'(?i)\b(?:six|nine|twelve) months|\byear ended\b',header):
                continue
            month = end.strftime('%B')
            day = str(end.day)
            month_day = rf'(?:{month}\s+{day}|{day}\s+{month})'
            if re.search(rf'\b{month_day}(?:\s+|\s*,\s*){end.year}\b', header, re.I):
                columns.append(x)
        if cik == '0000310764':
            columns = _stryker_columns(headers, end)
        if cik == '0000001800':
            # Abbott's reviewed calendar-quarter statement has exact month/day
            # and two years in its title, and explicit 3Q26-style columns.
            quarter = {(3,31):1,(6,30):2,(9,30):3,(12,31):4}.get((end.month,end.day))
            period_title = (r'(?i)\b'+({1:'First',2:'Second',3:'Third',4:'Fourth'}.get(quarter,'UNSUPPORTED'))
                            + r' Quarter Ended '+end.strftime('%B')+r'\s+'+str(end.day)+r',?\s+'+str(end.year)+r'\b')
            columns = []
            if re.search(period_title, scope):
                for x in range(1,width):
                    parts = {row[x] for row in headers if x<len(row) and row[x]}
                    if parts == {str(quarter)+'Q'+str(end.year)[2:]}:
                        columns.append(x)
        if not columns:
            continue
        group = ''
        for row,label in zip(grid[boundary:], labels[boundary:]):
            if re.search(r'(?i)weighted|shares (?:outstanding|used)',label):
                # PTC pairs each per-share amount with a separately labelled share count.
                if not (cik == '0000857005' and group == 'eps'
                        and label.casefold() == 'weighted average shares outstanding'):
                    group = 'shares'
            elif cik == '0001601046' and re.fullmatch(r'(?i)Diluted income \(loss\) per share:', label):
                group = 'total_diluted_eps'
            elif re.search(r'(?i)(?:earnings|income) per (?:common )?share',label) and group != 'total_diluted_eps':
                group = 'eps'
            metric = None
            if re.fullmatch(revenue_label,label):
                metric = 'revenue'
            elif (re.fullmatch(r'(?i)diluted(?:\s+(?:earnings|income)(?:\s+\(loss\))?\s+per\s+(?:common\s+)?share(?:\s*\(EPS\))?)?',label)
                  and (group == 'eps' or re.search(r'(?i)per (?:common )?share',label))):
                metric = 'epsGaapDiluted'
            elif label.casefold() == diluted_eps_label:
                metric = 'epsGaapDiluted'
            elif group == 'total_diluted_eps' and label.casefold() == 'net income per share':
                metric = 'epsGaapDiluted'
                group = None
            if metric is None:
                continue
            for x in columns:
                value = _number(row[x]) if x < len(row) else None
                if value is not None and (metric != 'revenue' or value >= 0):
                    values[metric].add(float(value * scale if metric=='revenue' else value))
    return {key: next(iter(found)) for key,found in values.items() if len(found)==1}

