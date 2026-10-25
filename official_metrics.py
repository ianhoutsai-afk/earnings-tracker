"""Exact-period official facts and explicitly labelled consolidated GAAP tables.

These readers never infer a fiscal quarter from a calendar frame, subtract annual
EPS, sum revenue components, or interpret adjusted/FFO/continuing EPS as net EPS.
"""
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import html

from official_sources import DATE, _date, _text

EPS_TAG = 'EarningsPerShareDiluted'
TOTAL_REVENUE_TAGS = ('Revenues', 'SalesRevenueNet', 'RevenuesNetOfInterestExpense')


def _empty(currency='USD'):
    return {'epsGaapDiluted': None, 'revenue': None, 'epsBasis': None,
            'currency': currency, 'epsVerificationStatus': 'pending',
            'revenueVerificationStatus': 'pending', 'metricLocators': {}}


def _select(candidates):
    """Equivalent rounded statements agree when their disclosed precision overlaps."""
    if not candidates:
        return None, 'pending', None
    lower = max(value - precision / 2 for value, precision, _ in candidates)
    upper = min(value + precision / 2 for value, precision, _ in candidates)
    if lower > upper:
        return None, 'conflict', None
    value, precision, locator = min(candidates, key=lambda row: row[1])
    return float(value), 'verified', {**locator,'precision':str(precision)}


def parse_companyfacts(payload, *, cik, period_end, accessions, today):
    result = _empty()
    if str(payload.get('cik', '')).lstrip('0') != str(cik).lstrip('0'):
        return result
    taxonomy = payload.get('facts', {}).get('us-gaap', {})
    for field, tags, unit, state_key in (
        ('epsGaapDiluted', (EPS_TAG,), 'USD/shares', 'epsVerificationStatus'),
        ('revenue', TOTAL_REVENUE_TAGS, 'USD', 'revenueVerificationStatus'),
    ):
        candidates = []
        for tag in tags:
            for fact in taxonomy.get(tag, {}).get('units', {}).get(unit, []):
                try:
                    duration = (date.fromisoformat(fact['end']) - date.fromisoformat(fact['start'])).days + 1
                    valid = (fact['end'] == period_end and 70 <= duration <= 110
                             and fact.get('accn') in accessions
                             and fact.get('form') in ('10-Q', '10-K', '10-Q/A', '10-K/A')
                             and date.fromisoformat(fact['filed']) <= today
                             and not isinstance(fact['val'], bool))
                    value = Decimal(str(fact['val']))
                    if not valid or not value.is_finite() or (field == 'revenue' and value < 0):
                        continue
                    candidates.append((value, Decimal('0.000000001'),
                                       {'tag': tag, 'accession': fact['accn'],
                                        'periodStart': fact['start'], 'periodEnd': fact['end'], 'unit': unit}))
                except (KeyError, TypeError, ValueError, InvalidOperation):
                    continue
        value, state, locator = _select(candidates)
        result[field], result[state_key] = value, state
        if locator:
            result['metricLocators'][field] = locator
    if result['epsGaapDiluted'] is not None:
        result['epsBasis'] = 'GAAP diluted'
    return result


def _grid(table):
    rows, spans = [], {}
    for tr in table.xpath('.//tr'):
        if next(tr.iterancestors('table'), None) is not table:
            continue
        cells, next_spans = {}, {}
        for column, (remaining, text) in spans.items():
            cells[column] = text
            if remaining > 1:
                next_spans[column] = (remaining - 1, text)
        column = 0
        for cell in tr.xpath('./td|./th'):
            while column in cells:
                column += 1
            text = ' '.join(_text(cell).split())
            try:
                width = min(100, max(1, int(cell.get('colspan', '1'))))
                height = min(100, max(1, int(cell.get('rowspan', '1'))))
            except ValueError:
                width, height = 1, 1
            for offset in range(width):
                cells[column + offset] = text
                if height > 1:
                    next_spans[column + offset] = (height - 1, text)
            column += width
        spans = next_spans
        if cells:
            rows.append([cells.get(i, '') for i in range(max(cells) + 1)])
    return rows


def _context(table):
    snippets = []
    node = table
    for _ in range(5):
        previous = node.getprevious()
        count = 0
        while previous is not None and count < 6:
            if not isinstance(previous.tag,str):
                previous = previous.getprevious()
                continue
            text = ' '.join(_text(previous).split())
            if previous.tag == 'table' or previous.xpath('.//table'):
                # A one-line layout table may be the statement's title/units.
                # Never cross another financial table to borrow its heading.
                if len(text) < 800 and re.search(r'(?i)(?:consolidated|combined) statements? of (?:income|operations|earnings)', text):
                    snippets.insert(0, text)
                break
            if re.search(r'(?i)notes? to|non-gaap reconciliation', text):
                break
            if text:
                snippets.insert(0, text)
            previous = previous.getprevious()
            count += 1
        if snippets or node.getparent() is None:
            break
        node = node.getparent()
    return ' '.join(snippets)[-2500:]


def _numeric(text):
    raw = text.replace('$', '').replace(',', '').replace('−', '-').replace('\xa0', '')
    raw = ''.join(raw.split())
    if raw.startswith('(') and raw.endswith(')'):
        raw = '-' + raw[1:-1]
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', raw):
        return None
    try:
        value = Decimal(raw)
        decimals = len(raw.rsplit('.', 1)[1]) if '.' in raw else 0
        return value, Decimal(10) ** -decimals
    except InvalidOperation:
        return None


def _target_header(text, period_end, fiscal_year, fiscal_quarter):
    normalized = ' '.join(text.split())
    ends = set()
    for match in re.finditer(DATE, normalized, re.I):
        try:
            ends.add(_date(match[0]).isoformat())
        except ValueError:
            pass
    for match in re.finditer(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b', normalized):
        try:
            year = int(match[3]) + (2000 if len(match[3]) == 2 else 0)
            ends.add(date(year, int(match[1]), int(match[2])).isoformat())
        except ValueError:
            pass
    quarter_duration = bool(re.search(r'(?i)three months|quarter(?:s|ly)?\s+ended', normalized))
    cumulative = bool(re.search(r'(?i)six months|nine months|twelve months|year ended|years ended', normalized))
    if period_end in ends and quarter_duration and not cumulative:
        return True
    if fiscal_year and fiscal_quarter:
        token = rf'(?i)\b(?:Q{fiscal_quarter}\s*(?:FY\s*)?(?:{fiscal_year}|{str(fiscal_year)[-2:]})|{fiscal_quarter}Q\s*(?:{fiscal_year}|{str(fiscal_year)[-2:]}))\b'
        return bool(re.search(token, normalized)) and not cumulative
    return False


def parse_statement_metrics(document, period_end, *, currency=None,
                            fiscal_year=None, fiscal_quarter=None):
    result = _empty(currency)
    if currency != 'USD':
        return result
    tree = html.fromstring(document.encode() if isinstance(document, str) else document)
    for node in tree.xpath('//script|//style'):
        node.drop_tree()
    candidates = {'epsGaapDiluted': [], 'revenue': []}
    for table_index, table in enumerate(tree.xpath('//table'), 1):
        rows = _grid(table)
        if not rows:
            continue
        context = _context(table)
        leading = ' '.join(' '.join(row) for row in rows[:5])
        statement = bool(re.search(r'(?i)(?:consolidated|combined) statements? of (?:income|operations|earnings)', context + ' ' + leading))
        gaap_table = bool(re.search(r'(?i)\bGAAP Metrics\b', leading))
        if not statement and not gaap_table and not any(re.search(r'(?i)total (?:net )?revenue.*\(GAAP\)', ' '.join(r[:2])) for r in rows):
            continue
        header_rows = rows[:min(10, len(rows))]
        width = max(map(len, rows))
        columns = [col for col in range(width) if _target_header(
            ' '.join(row[col] for row in header_rows if col < len(row)),
            period_end, fiscal_year, fiscal_quarter)]
        if not columns:
            continue
        unit_context = context + ' ' + leading
        scale = None
        if re.search(r'(?i)\bin (?:USD )?millions\b|\$s? in millions', unit_context):
            scale = Decimal(1000000)
        elif re.search(r'(?i)\bin (?:USD )?thousands\b|\$s? in thousands', unit_context):
            scale = Decimal(1000)
        elif re.search(r'(?i)\b(?:in|amounts in) (?:U\.S\. |US )?dollars\b',unit_context):
            scale = Decimal(1)
        eps_parent = False
        active_gaap = statement
        for row_index, row in enumerate(rows, 1):
            label_parts = []
            for text in row:
                if _numeric(text) is not None:
                    break
                if text and text.strip() not in ('$', '(', ')'):
                    label_parts.append(text)
            label = ' '.join(dict.fromkeys(label_parts)).strip(' :')
            if not label:
                continue
            if re.search(r'(?i)^non[ -]?gaap|^adjusted metrics', label):
                active_gaap = False
            elif re.search(r'(?i)^GAAP Metrics', label):
                active_gaap = True
            excluded = bool(re.search(r'(?i)adjusted|non[ -]?gaap|ffo|continuing operations|continuing EPS|normalized|core earnings', label))
            revenue_label = re.sub(r'\s*\((?:GAAP|\d+)\)\s*', '', label, flags=re.I)
            revenue = bool(re.fullmatch(r'(?i)(?:total )?(?:net )?(?:operating )?(?:revenues?|sales)(?:,? net of interest expense)?', revenue_label))
            per_share = bool(re.search(r'(?i)(?:earnings|income|loss).*per (?:common )?share|per share.*(?:earnings|income|loss)', label))
            share_count = bool(re.search(r'(?i)weighted.average|number of shares|shares (?:of .* )?outstanding|shares.*(?:used|comput|calculat)',label))
            if excluded or share_count or re.search(r'(?i)funds from operations|discontinued operations', label):
                eps_parent = False
            elif per_share and not excluded:
                eps_parent = True
            diluted_eps = not excluded and not share_count and ((per_share and 'diluted' in label.lower()) or
                                            (bool(re.fullmatch(r'(?i)diluted', label)) and eps_parent))
            eligible_revenue = scale is not None and revenue and not excluded and (active_gaap or bool(re.search(r'(?i)\(GAAP\)', label)))
            if not diluted_eps and not eligible_revenue:
                continue
            for column in columns:
                if column >= len(row):
                    continue
                parsed = _numeric(row[column])
                if parsed is None:
                    continue
                value, precision = parsed
                if diluted_eps and active_gaap:
                    candidates['epsGaapDiluted'].append((value, precision,
                        {'table': table_index, 'row': row_index, 'column': column + 1, 'label': label}))
                if eligible_revenue and value >= 0:
                    candidates['revenue'].append((value * scale, precision * scale,
                        {'table': table_index, 'row': row_index, 'column': column + 1, 'label': label, 'scale': int(scale)}))
    for field, state_key in [('epsGaapDiluted', 'epsVerificationStatus'), ('revenue', 'revenueVerificationStatus')]:
        value, state, locator = _select(candidates[field])
        result[field], result[state_key] = value, state
        if locator:
            result['metricLocators'][field] = locator
    if result['epsGaapDiluted'] is not None:
        result['epsBasis'] = 'GAAP diluted'
    return result
