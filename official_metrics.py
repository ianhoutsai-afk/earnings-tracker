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
            'revenueVerificationStatus': 'pending', 'metricLocators': {}, 'metricConflicts': {}}


def _conflict_evidence(candidates):
    return [{'value':float(value),'precision':str(precision),'locator':locator}
            for value,precision,locator in candidates]


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
        if state == 'conflict':
            result['metricConflicts'][field] = _conflict_evidence(candidates)
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
    if re.search(r'(?i)non[ -]?gaap|adjusted|adjustments|comparable hotel|percent|%|change', normalized):
        return False
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
    quarter_duration = bool(re.search(r'(?i)three months|quarter(?:ly)?\s+ended', normalized))
    cumulative = bool(re.search(r'(?i)six months|nine months|twelve months|year ended|years ended|(?:two|three|four) (?:fiscal )?quarters|year.to.date', normalized))
    years = [part.strip() for part in text.splitlines() if re.fullmatch(r'20\d{2}',part.strip())]
    if years and years[-1] != period_end[:4] and ends:
        return False
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
    partial_sales_tables = set()
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
        if any(re.fullmatch(r'(?i)financial services revenues?', row[0].strip(' :')) for row in rows if row):
            # This income statement reports a second revenue stream below net sales.
            # Net sales alone are not the issuer's consolidated revenue total.
            partial_sales_tables.add(table_index)
        def data_row(row):
            values = [cell for cell in row if _numeric(cell) is not None]
            return bool(values) and (any(not re.fullmatch(r'20\d{2}',cell.strip()) for cell in values)
                                     or '$' in row)
        first_data = next((i for i,row in enumerate(rows) if data_row(row)),len(rows))
        header_rows = rows[:first_data]
        width = max(map(len, rows))
        percentage_columns = set()
        # The first financial line establishes dedicated percentage columns.
        # Later margin/tax-rate rows reuse ordinary dollar columns for percentages.
        for row in rows[first_data:first_data+1]:
            for col,cell in enumerate(row):
                if cell.strip() == '%':
                    if col and _numeric(row[col-1]) is not None:
                        percentage_columns.add(col-1)
                        if col>1 and row[col-2]==row[col-1]:percentage_columns.add(col-2)
        columns = [col for col in range(width) if col not in percentage_columns and _target_header(
            '\n'.join(row[col] for row in header_rows if col < len(row)),
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
        shares_section = False
        segment_section = False
        seen_data = False
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
            if seen_data and re.search(r'(?i)(?:three|six|nine|twelve) months ended|fiscal quarters ended', ' '.join(row)):
                # Repeated period blocks must not inherit the preceding header.
                break
            if re.search(r'(?i)non[ -]?gaap|as adjusted|adjusted basis|^adjusted metrics', label):
                active_gaap = False
            elif re.search(r'(?i)^GAAP Metrics', label):
                active_gaap = True
            excluded = bool(re.search(r'(?i)adjusted|non[ -]?gaap|ffo|continuing operations|discontinued operations|continuing EPS|normalized|core earnings', label))
            revenue_label = re.sub(r'\s*\((?:GAAP|\d+)\)\s*', '', label, flags=re.I)
            revenue = bool(re.fullmatch(r'(?i)(?:total )?(?:net )?(?:operating )?(?:revenues?|sales)(?:,? net of interest expense)?', revenue_label))
            per_share = bool(re.search(r'(?i)(?:earnings|income|loss).*per (?:basic |diluted )?(?:common )?share|per share.*(?:earnings|income|loss)', label))
            share_count = bool(re.search(r'(?i)weighted.average|average common shares|number of shares|shares (?:of .* )?outstanding|shares.*(?:used|comput|calculat)',label))
            if share_count:
                shares_section = True
            elif per_share and not re.search(r'(?i)^(?:for\b|in\s+(?:computing|calculating|determining)\b)', label) and not any(_numeric(cell) for cell in row) and not excluded:
                shares_section = False
            if re.search(r'(?i)homebuilding|mortgage banking|business unit|segment',label) and not any(_numeric(cell) for cell in row):
                segment_section = True
            if excluded or share_count or re.search(r'(?i)funds from operations|discontinued operations', label):
                eps_parent = False
            elif per_share and not excluded:
                eps_parent = True
            diluted_eps = not excluded and not shares_section and ((per_share and 'diluted' in label.lower()) or
                                            (bool(re.fullmatch(r'(?i)diluted(?:\s+\(?\d+\)?)?', label)) and eps_parent))
            eligible_revenue = scale is not None and revenue and not excluded and not segment_section and (active_gaap or bool(re.search(r'(?i)\(GAAP\)', label)))
            if not diluted_eps and not eligible_revenue:
                continue
            for column in columns:
                if column >= len(row):
                    continue
                parsed = _numeric(row[column])
                if parsed is None:
                    continue
                value, precision = parsed
                seen_data = True
                if diluted_eps and active_gaap:
                    candidates['epsGaapDiluted'].append((value, precision,
                        {'table': table_index, 'row': row_index, 'column': column + 1, 'label': label}))
                if eligible_revenue and value >= 0:
                    candidates['revenue'].append((value * scale, precision * scale,
                        {'table': table_index, 'row': row_index, 'column': column + 1, 'label': label, 'scale': int(scale)}))
    for field, state_key in [('epsGaapDiluted', 'epsVerificationStatus'), ('revenue', 'revenueVerificationStatus')]:
        if field == 'revenue':
            candidates[field] = [c for c in candidates[field] if not (
                c[2]['table'] in partial_sales_tables
                and re.fullmatch(r'(?i)(?:total )?net sales', c[2]['label']))]
            # A consolidated total includes net sales/operating-revenue components.
            totals = {loc['table'] for _,_,loc in candidates[field]
                      if re.fullmatch(r'(?i)total (?:net )?revenues?(?:\s*\(GAAP\))?',loc['label'])}
            candidates[field] = [c for c in candidates[field] if c[2]['table'] not in totals
                or re.fullmatch(r'(?i)total (?:net )?revenues?(?:\s*\(GAAP\))?',c[2]['label'])]
            net_sales = {loc['table'] for _,_,loc in candidates[field]
                         if re.fullmatch(r'(?i)(?:total )?net sales',loc['label'])}
            candidates[field] = [c for c in candidates[field] if c[2]['table'] not in net_sales
                                 or not re.fullmatch(r'(?i)(?:total )?sales',c[2]['label'])]
        value, state, locator = _select(candidates[field])
        result[field], result[state_key] = value, state
        if locator:
            result['metricLocators'][field] = locator
        if state == 'conflict':
            result['metricConflicts'][field] = _conflict_evidence(candidates[field])
    if result['epsGaapDiluted'] is not None:
        result['epsBasis'] = 'GAAP diluted'
    return result
