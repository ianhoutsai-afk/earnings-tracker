"""Exact-period official facts and explicitly labelled consolidated GAAP tables.

These readers never infer a fiscal quarter from a calendar frame, subtract annual
EPS, sum revenue components, or interpret adjusted/FFO/continuing EPS as net EPS.
"""
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import html

from official_sources import DATE, _date, _text, _fiscal_identity, _statement_scope
from official_paged_statement import statement_page, page_candidates
from official_narratives import net_income_eps_candidates

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


def _grid(table, *, include_nodes=False):
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
            text = cell if include_nodes else ' '.join(_text(cell).split())
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
            rows.append([cells.get(i, None if include_nodes else '') for i in range(max(cells) + 1)])
    return rows


def _context(table):
    snippets = []
    node = table
    barrier=re.compile(r'(?i)\bnotes?\s+(?:\d+|to\b)|non-gaap reconciliation|balance sheets?|statements? of (?:cash flows|financial position)')
    for _ in range(5):
        boundary = False
        if node.getparent() is not None and barrier.search(node.getparent().text or ''):
            break
        previous = node.getprevious()
        count = 0
        while previous is not None and count < 6:
            if barrier.search(previous.tail or ''):
                boundary = True
                break
            if not isinstance(previous.tag,str):
                previous = previous.getprevious()
                continue
            text = ' '.join(_text(previous).split())
            if previous.tag == 'table' or previous.xpath('.//table'):
                # A one-line layout table may be the statement's title/units.
                # Never cross another financial table to borrow its heading.
                layout_tables=[previous] if previous.tag=='table' else previous.xpath('.//table')
                layout_rows=[row for row in _grid(layout_tables[0]) if any(row)] if len(layout_tables)==1 else []
                without_dates=re.sub(DATE,'',text,flags=re.I)
                if (len(text) < 800 and not barrier.search(text) and _statement_scope(text) == 'consolidated'
                        and len(layout_tables) == 1 and len(layout_rows) <= 4
                        and not re.search(r'\d',without_dates) and not previous.xpath('.//*[@contextref]')):
                    snippets.insert(0, text)
                boundary = True
                break
            if barrier.search(text):
                boundary = True
                break
            if text:
                snippets.insert(0, text)
                count += 1
            previous = previous.getprevious()
        if boundary or _statement_scope(' '.join(snippets)) is not None or node.getparent() is None:
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


def _net_revenue_total(label):
    clean=re.sub(r'\s*\((?:GAAP|\d+)\)\s*',' ',label,flags=re.I).strip()
    return bool(re.fullmatch(r'(?i)total net revenues?|(?:total )?revenues?,? net of interest expense',clean))


def _header_dates(text):
    normalized=' '.join(text.split())
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
    return ends


def _target_header(text, period_end, fiscal_year, fiscal_quarter):
    normalized = ' '.join(text.split())
    normalized = re.sub(r'(?i)\b(three|six|nine|twelve)-months\b',r'\1 months',normalized)
    if re.search(r'(?i)non[ -]?gaap|adjusted|adjustments|pro[ -]?forma|comparable hotel|percent|%|change|\bguidance\b|\bforecast\b|\bvariance\b', normalized):
        return False
    ends = _header_dates(normalized)
    quarter_duration = bool(re.search(r'(?i)three months|quarter(?:ly)?\s+ended', normalized))
    cumulative = bool(re.search(r'(?i)six months|nine months|twelve months|year ended|years ended|full[ -](?:fiscal[ -])?year|(?:two|three|four) (?:fiscal )?quarters|year.to.date', normalized))
    years = [part.strip() for part in text.splitlines() if re.fullmatch(r'20\d{2}',part.strip())]
    if years and years[-1] != period_end[:4] and ends:
        return False
    if period_end in ends and quarter_duration and not cumulative:
        return True
    if fiscal_year and fiscal_quarter:
        token = rf'(?i)\b(?:Q{fiscal_quarter}\s*(?:FY\s*)?(?:{fiscal_year}|{str(fiscal_year)[-2:]})|{fiscal_quarter}Q\s*(?:{fiscal_year}|{str(fiscal_year)[-2:]}))\b'
        if re.search(token, normalized) and not cumulative:return True
        if ends and ends != {period_end}:return False
        return _fiscal_identity(normalized) == (fiscal_year,fiscal_quarter) and not cumulative
    return False


def _scope_leading(rows):
    snippets=[]
    for row in rows[:5]:
        mixed_basis=(any(re.fullmatch(r'(?i)as reported',cell.strip()) for cell in row)
                     and any(re.fullmatch(r'(?i)pro[ -]?forma',cell.strip()) for cell in row))
        # A basis label in a mixed As Reported / Pro Forma header belongs to
        # its column. It cannot turn the entire original statement into a
        # recast table. Preserve the original header for column validation.
        snippets.extend(cell for cell in row if not (mixed_basis and re.fullmatch(r'(?i)pro[ -]?forma',cell.strip())))
    return ' '.join(snippets)


def _reported_basis_columns(rows):
    allowed=None
    for row in rows:
        if any(re.search(r'(?i)\bpro[ -]?forma(?![a-z])',cell) for cell in row):
            reported={col for col,cell in enumerate(row) if re.fullmatch(
                r'(?i)as reported(?:\s*(?:\([a-z0-9]{1,3}\)|[¹²³⁴⁵⁶⁷⁸⁹⁰]))*',cell.strip())}
            allowed=reported if allowed is None else allowed & reported
    return allowed


def discover_statement_period(document, event_date, fiscal_year, fiscal_quarter):
    """Read an explicit current quarter end from a consolidated income statement."""
    if not fiscal_year or fiscal_quarter not in (1,2,3,4):return None
    event=date.fromisoformat(event_date)
    tree=html.fromstring(document.encode() if isinstance(document,str) else document)
    candidates={}
    for table_index,table in enumerate(tree.xpath('//table'),1):
        rows=_grid(table)
        if not rows:continue
        leading=_scope_leading(rows)
        if _statement_scope(_context(table)+' '+leading) != 'consolidated':continue
        def data_row(row):
            values=[cell for cell in row if _numeric(cell) is not None]
            return bool(values) and (any(not re.fullmatch(r'20\d{2}',cell.strip()) for cell in values) or '$' in row)
        first=next((i for i,r in enumerate(rows) if data_row(r)),len(rows))
        reported_columns=_reported_basis_columns(rows[:first])
        for col in range(max(map(len,rows))):
            if reported_columns is not None and col not in reported_columns:continue
            header='\n'.join(r[col] for r in rows[:first] if col<len(r))
            if not re.search(r'(?i)three[ -]months|quarter(?:ly)?\s+ended',header):continue
            identity=_fiscal_identity(header)
            if identity[0] is not None and identity != (fiscal_year,fiscal_quarter):continue
            for end in _header_dates(header):
                if 0<(event-date.fromisoformat(end)).days<=180 and _target_header(header,end,fiscal_year,fiscal_quarter):
                    candidates.setdefault(end,{'table':table_index,'column':col+1,'header':header})
    page=statement_page(tree,fiscal_year,fiscal_quarter)
    if page and 0<(event-date.fromisoformat(page['periodEnd'])).days<=180:
        candidates.setdefault(page['periodEnd'],page['locator'])
    if len(candidates)!=1:return None
    end=next(iter(candidates))
    return {'periodEnd':end,'locator':candidates[end]}


def _percentage_columns(row):
    columns=set()
    for col,cell in enumerate(row):
        if cell.strip()=='%' and col and _numeric(row[col-1]) is not None:
            columns.add(col-1)
            if col>1 and row[col-2]==row[col-1]:columns.add(col-2)
    return columns


def _eps_calculation_input(label):
    return bool(re.fullmatch(r'(?i)(?:net )?(?:income|earnings|loss) for (?:basic |diluted )?earnings per (?:common )?share(?: of common stock)?',label)
        or re.search(r'(?i)\b(?:numerator|denominator)\b',label) or (
        re.search(r'(?i)\b(?:income|earnings|loss)\b',label)
        and re.search(r'(?i)\b(?:calculat\w*|comput\w*|determin\w*)\b',label)
        and re.search(r'(?i)\b(?:per\b.*\bshare|EPS)\b',label)))


def parse_statement_metrics(document, period_end, *, currency=None,
                            fiscal_year=None, fiscal_quarter=None, issuer_cik=None):
    result = _empty(currency)
    if currency != 'USD':
        return result
    tree = html.fromstring(document.encode() if isinstance(document, str) else document)
    for node in tree.xpath('//script|//style'):
        node.drop_tree()
    candidates = {'epsGaapDiluted': [], 'revenue': []}
    statement_period_proof=None
    partial_sales_tables = set()
    for table_index, table in enumerate(tree.xpath('//table'), 1):
        rows = _grid(table)
        if not rows:
            continue
        context = _context(table)
        leading = ' '.join(' '.join(row) for row in rows[:5])
        scope=_statement_scope(context+' '+_scope_leading(rows))
        if scope in ('nonconsolidated','recast'):
            result.setdefault('excludedStatementTables',[]).append({'table':table_index,
                'reason':'supplemental_recast_statement' if scope=='recast' else 'nonconsolidated_statement','heading':context[-700:]+' '+leading[:300]})
            continue
        statement = scope == 'consolidated'
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
            percentage_columns.update(_percentage_columns(row))
        reported_columns=_reported_basis_columns(header_rows)
        columns = [col for col in range(width) if col not in percentage_columns
            and (reported_columns is None or col in reported_columns) and _target_header(
            '\n'.join(row[col] for row in header_rows if col < len(row)),
            period_end, fiscal_year, fiscal_quarter)]
        if not columns:
            continue
        if statement and statement_period_proof is None:
            col=columns[0]
            statement_period_proof={'table':table_index,'column':col+1,'periodEnd':period_end,
                'header':'\n'.join(row[col] for row in header_rows if col<len(row))}
        unit_context = context + ' ' + leading
        comprehensive_title=re.search(r'(?i)\bstatements?\s+of\s+(?:consolidated\s+)?comprehensive\s+(?:income|earnings|loss)\b',unit_context)
        comprehensive_statement=bool(comprehensive_title and not re.match(
            r'(?i)\s+and\s+(?:net\s+)?(?:income|earnings|loss)\b',unit_context[comprehensive_title.end():]))
        scale = None
        if re.search(r'(?i)\bin (?:USD )?millions\b|\$s? in millions|\$\s*million\b', unit_context):
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
        comprehensive_section = comprehensive_statement
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
            if re.search(r'(?i)^(?:(?:as\s+(?:a\s+)?)?percent(?:age)?s?(?:\s*\(%\))?\s+of\b|%\s+of\b)',label):
                # A later ratio block cannot inherit the dollar statement's
                # period headers or millions/thousands scaling.
                break
            if seen_data and re.search(r'(?i)(?:three|six|nine|twelve) months ended|fiscal quarters ended', ' '.join(row)):
                # Repeated period blocks must not inherit the preceding header.
                break
            if re.search(r'(?i)non[ -]?gaap|as adjusted|adjusted basis|^adjusted metrics', label):
                active_gaap = False
            elif re.search(r'(?i)^GAAP Metrics', label):
                active_gaap = True
            numerator=_eps_calculation_input(label)
            if numerator:
                for col in columns:
                    parsed=_numeric(row[col]) if col<len(row) else None
                    if parsed:
                        result.setdefault('excludedEpsInputs',[]).append({'value':float(parsed[0]),'periodEnd':period_end,
                            'reason':'eps_calculation_input','locator':{'table':table_index,
                            'row':row_index,'column':col+1,'label':label}})
            excluded = numerator or bool(re.search(r'(?i)adjusted|non[ -]?gaap|comprehensive|ffo|continuing operations|discontinued operations|continuing EPS|normalized|core earnings|excluding\s+(?:specified|special|certain)\s+(?:items|charges)', label))
            revenue_label = re.sub(r'\s*\((?:GAAP|\d+)\)\s*', '', label, flags=re.I)
            revenue = bool(re.fullmatch(r'(?i)(?:total )?(?:net )?(?:operating )?(?:revenues?|sales)(?:,? net of interest expense)?', revenue_label))
            per_share = bool(re.search(r'(?i)(?:earnings|income|loss).*per (?:basic |diluted )?(?:common )?share|per share.*(?:earnings|income|loss)', label))
            if re.search(r'(?i)\bcomprehensive\b',label):
                comprehensive_section=True
            elif per_share and not excluded and re.match(r'(?i)^(?:diluted\s+)?net\s+(?:income|earnings|loss)\b',label):
                comprehensive_section=False
            elif (not excluded and not per_share and re.fullmatch(
                    r'(?i)net\s+(?:income|earnings|loss)(?:\s*\(loss\)|\s*\(income\))?(?:\s+attributable\s+to\s+.+)?',label)
                    and any(col<len(row) and _numeric(row[col]) is not None for col in columns)):
                # Some main income statements use a comprehensive-income
                # title but explicitly establish net income before generic
                # EPS. A subsequent comprehensive-income line resets this.
                comprehensive_section=False
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
                if column >= len(row) or column in _percentage_columns(row):
                    continue
                parsed = _numeric(row[column])
                if parsed is None:
                    continue
                value, precision = parsed
                seen_data = True
                if diluted_eps and active_gaap and not comprehensive_section:
                    candidates['epsGaapDiluted'].append((value, precision,
                        {'table': table_index, 'row': row_index, 'column': column + 1, 'label': label}))
                if eligible_revenue and value >= 0:
                    candidates['revenue'].append((value * scale, precision * scale,
                        {'table': table_index, 'row': row_index, 'column': column + 1, 'label': label, 'scale': int(scale)}))
    page=statement_page(tree,fiscal_year,fiscal_quarter)
    candidates['epsGaapDiluted'].extend(net_income_eps_candidates(tree,issuer_cik,
        fiscal_year,fiscal_quarter,statement_period_proof,_numeric))
    page_values=page_candidates(page,_numeric) if page and page['periodEnd']==period_end else {}
    for field, state_key in [('epsGaapDiluted', 'epsVerificationStatus'), ('revenue', 'revenueVerificationStatus')]:
        if field == 'revenue':
            candidates[field] = [c for c in candidates[field] if not (
                c[2]['table'] in partial_sales_tables
                and re.fullmatch(r'(?i)(?:total )?net sales', c[2]['label']))]
            # A consolidated total includes net sales/operating-revenue components.
            net_totals={loc['table'] for _,_,loc in candidates[field] if _net_revenue_total(loc['label'])}
            candidates[field]=[c for c in candidates[field] if c[2]['table'] not in net_totals
                               or _net_revenue_total(c[2]['label'])]
            totals = {loc['table'] for _,_,loc in candidates[field]
                      if re.fullmatch(r'(?i)total (?:net )?revenues?(?:\s*\(GAAP\))?',loc['label'])}
            candidates[field] = [c for c in candidates[field] if c[2]['table'] not in totals
                or re.fullmatch(r'(?i)total (?:net )?revenues?(?:\s*\(GAAP\))?',c[2]['label'])]
            net_sales = {loc['table'] for _,_,loc in candidates[field]
                         if re.fullmatch(r'(?i)(?:total )?net sales',loc['label'])}
            candidates[field] = [c for c in candidates[field] if c[2]['table'] not in net_sales
                                 or not re.fullmatch(r'(?i)(?:total )?sales',c[2]['label'])]
        # Keep page transcripts separate from table filtering; their columns
        # have been validated by the registered layout reader.
        candidates[field].extend(page_values.get(field,[]))
        value, state, locator = _select(candidates[field])
        result[field], result[state_key] = value, state
        if locator:
            result['metricLocators'][field] = locator
        if state == 'conflict':
            result['metricConflicts'][field] = _conflict_evidence(candidates[field])
    if result['epsGaapDiluted'] is not None:
        result['epsBasis'] = 'GAAP diluted'
    return result
