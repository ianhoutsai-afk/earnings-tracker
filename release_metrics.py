"""Explicit quarterly GAAP statement columns for reviewed USD issuer layouts.

Supported issuer review: Microsoft, Meta, Stryker and Tesla shareholder
statements. Do not generalize currency or taxonomy
assumptions to unreviewed issuers. Q4 is read directly, never subtracted.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from lxml import html

SUPPORTED_ISSUERS = {'0000789019', '0001326801', '0000310764'}

def _text(node):
    return ' '.join(' '.join(node.itertext()).split())

def _grid(table):
    """Expand HTML header spans so quarter/year headings retain their columns."""
    occupied = {}
    output = []
    rows = table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr')
    for y, row in enumerate(rows[:1000]):
        x = 0
        for cell in row.xpath('./td|./th'):
            while (y, x) in occupied:
                x += 1
            width, height = int(cell.get('colspan', '1')), int(cell.get('rowspan', '1'))
            if not (1 <= width <= 128 and 1 <= height <= 1000 and x + width <= 128):
                raise ValueError('Unsupported statement span')
            hidden = 'display:none' in cell.get('style', '').replace(' ', '').lower()
            value = '' if hidden else _text(cell)
            for dy in range(height):
                for dx in range(width):
                    occupied[y+dy, x+dx] = value
            x += width
        length = max((col+1 for rownum,col in occupied if rownum == y), default=0)
        output.append([occupied.get((y, col), '') for col in range(length)])
    return output

def _scope(table):
    """Use a nearby income-statement heading, bounded by notes and other tables."""
    prefix = []
    # Some original exhibits put the statement title in a full-width table row.
    # Use an exact title before the data, never a loose mention in a note.
    first_rows = table.xpath('./tr|./thead/tr|./tbody/tr')[:8]
    title_pattern = r'(?i)(?:(?:condensed|consolidated|combined)\s+)*(?:statements? of (?:income|operations|earnings)|income statements?)'
    header_text = ' '.join(_text(row) for row in first_rows)
    for row in first_rows:
        cells = row.xpath('./td|./th')
        if len(cells)==1 and re.fullmatch(title_pattern, _text(cells[0])):
            if re.search(r'(?i)non.gaap|adjusted|comprehensive|segment|notes?\s+(?:\d+|to\b)', header_text):
                return None
            return header_text
    caption = table.find('caption')
    if caption is not None:
        prefix.append(_text(caption))
    current = table
    for _ in range(4):
        previous = current.getprevious()
        for _ in range(8):
            if previous is None:
                break
            if previous.tag == 'table' or previous.xpath('.//table'):
                return None
            text = _text(previous)
            prefix.append(text)
            if re.search(r'(?i)non.gaap|adjusted|comprehensive|segment|notes?\s+(?:\d+|to\b)|balance sheet|cash flow', text):
                return None
            if re.fullmatch(r'(?i)(?:(?:condensed|consolidated|combined)\s+)*(?:statements? of (?:income|operations|earnings)|income statements?)', text):
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
    if caption is not None and re.fullmatch(r'(?i)(?:(?:condensed|consolidated|combined)\s+)*(?:statements? of (?:income|operations|earnings)|income statements?)', _text(caption)):
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
    dates = {text for text in shared if re.fullmatch(period, text, re.I)}
    if len(dates) != 1:
        return []
    columns = []
    for x in range(1, max(map(len, headers), default=0)):
        # The common title lists all durations; only the column's own duration
        # and year may choose a quarter. Percent-change columns have no year.
        parts = [row[x] for row in headers if x < len(row) and row[x] and row[x] not in shared]
        if ('Three Months' in parts and str(end.year) in parts
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
        if not text.startswith(units) or 'STATEMENTOFOPERATIONS(Unaudited)' not in re.sub(r'\s+', '', text):
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
    values = {'revenue': set(), 'epsGaapDiluted': set()}
    for table in tree.xpath('//table'):
        if table.xpath('.//table'):
            continue
        scope = _scope(table)
        if scope is None:
            continue
        try:
            grid = _grid(table)
        except (ValueError, TypeError):
            continue
        labels = [next((value for value in row if value), '') for row in grid]
        boundary = next((i for i,label in enumerate(labels) if re.fullmatch(r'(?i)(?:total\s+)?(?:net\s+)?(?:revenues?|sales)\s*:?',label)), None)
        if boundary is None:
            continue
        headers = grid[:boundary]
        units = scope+' '+' '.join(' '.join(row) for row in headers)
        if not re.search(r'(?i)\bin millions\b', units) and not (cik == '0000310764' and re.search(r'(?i)\bmillions of dollars\b', units)):
            continue
        width = max(map(len,grid), default=0)
        columns = []
        for x in range(1,width):
            header = ' '.join(dict.fromkeys(row[x] for row in headers if x < len(row) and row[x]))
            if not re.search(r'(?i)\bthree months ended\b',header) or re.search(r'(?i)\b(?:six|nine|twelve) months|\byear ended\b',header):
                continue
            month = end.strftime('%B')
            if re.search(r'(?i)\b'+month+r'\s+'+str(end.day)+r'\s*,?\s+'+str(end.year)+r'\b',header):
                columns.append(x)
        if cik == '0000310764':
            columns = _stryker_columns(headers, end)
        if not columns:
            continue
        group = ''
        for row,label in zip(grid[boundary:], labels[boundary:]):
            if re.search(r'(?i)weighted|shares (?:outstanding|used)',label):
                group = 'shares'
            elif re.search(r'(?i)(?:earnings|income) per share',label):
                group = 'eps'
            metric = None
            if re.fullmatch(r'(?i)(?:total\s+)?(?:net\s+)?(?:revenues?|sales)\s*:?',label):
                metric = 'revenue'
            elif (re.fullmatch(r'(?i)diluted(?:\s+(?:earnings|income)\s+per\s+share(?:\s*\(EPS\))?)?',label)
                  and (group == 'eps' or 'per share' in label.lower())):
                metric = 'epsGaapDiluted'
            if metric is None:
                continue
            for x in columns:
                value = _number(row[x]) if x < len(row) else None
                if value is not None and (metric != 'revenue' or value >= 0):
                    values[metric].add(float(value * 1000000 if metric=='revenue' else value))
    return {key: next(iter(found)) for key,found in values.items() if len(found)==1}

