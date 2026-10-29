"""Issuer-registered net-income/EPS clauses backed by an exact-period statement."""
import re

from official_sources import QUARTERS, _text


def _inherited_scope(node):
    parts=[]
    size=0
    current=node
    while current.getparent() is not None:
        parent=current.getparent()
        texts=[parent.text or '']
        sibling=current.getprevious()
        while sibling is not None:
            if isinstance(sibling.tag,str):texts.append(_text(sibling))
            sibling=sibling.getprevious()
        for text in texts:
            size+=len(text)
            if size>4000:return None
            if text.strip():parts.append(text)
        current=parent
    return ' '.join(parts)


def net_income_eps_candidates(tree, issuer_cik, fiscal_year, fiscal_quarter, period_proof, numeric):
    if (str(issuer_cik).lstrip('0') != '1014473' or not period_proof
            or not isinstance(fiscal_year,int) or fiscal_quarter not in (1,2,3,4)):
        return []
    # Verisign's comprehensive-income table does not itself establish net EPS.
    # Its original release explicitly pairs current net income and diluted EPS
    # in one sentence, before the prior-year comparison. Register that precise
    # disclosure layout rather than reclassifying comprehensive/continuing EPS.
    money=r'\$[\d,]+(?:\.\d+)?'
    pattern=re.compile(r'^VeriSign, Inc\. and (?:its )?subsidiaries \([“"]Verisign[”"]\) '
        r'reported revenue of '+money+r' million for the (?P<quarter>first|second|third|fourth) quarter of '
        r'(?P<year>20\d{2}), (?:up|down) \d+(?:\.\d+)? percent from the same quarter in (?P<prior>20\d{2})\. '
        r'Operating income was '+money+r' million for the (?P=quarter) quarter of (?P=year), compared to '
        +money+r' million for the same quarter of (?P=prior)\. '
        r'(?P<epsClause>Verisign reported net income of '+money+r' million and '
        r'diluted earnings per share \(diluted [“"]EPS[”"]\) of \$(?P<eps>-?\d+(?:\.\d+)?) '
        r'for the (?P=quarter) quarter of (?P=year), compared to net income of '+money+r' million '
        r'and diluted EPS of '+money+r' for the same quarter (?:in|of) (?P=prior)\.)(?=\s|$)')
    candidates=[]
    for paragraph,node in enumerate(tree.xpath('//div[not(descendant::div or descendant::p)]|//p[not(descendant::p)]'),1):
        if any(a.tag=='table' for a in node.iterancestors()):continue
        text=' '.join(_text(node).split())
        match=pattern.match(text)
        if not match or (int(match['year']),QUARTERS[match['quarter']]) != (fiscal_year,fiscal_quarter):continue
        if int(match['prior']) != fiscal_year-1:continue
        scope=_inherited_scope(node)
        if scope is None:return []
        if re.search(r'(?i)\badjusted\b|non[ -]?gaap|\bsegments?\b|\bunconsolidated\b|\b(?:Canadian|Australian|Hong Kong|Singapore|New Zealand)\s+dollars\b|\b(?:CAD|EUR|GBP|JPY|AUD|HKD|CNY|RMB|SGD|CHF|euros|yen|sterling|renminbi)\b',scope):continue
        currency_claims=re.finditer(r'(?i)\b(?:expressed|denominated|stated|presented)\s+in\s+([^;]{1,100})',scope)
        if any(not re.match(r'(?i)(?:USD\b|U\.S\. dollars\b|United States dollars\b|US dollars\b)',m[1]) for m in currency_claims):continue
        parsed=numeric(match['eps'])
        if parsed is None:continue
        value,precision=parsed
        candidates.append((value,precision,{'layout':'verisign_net_income_eps_clause_v1',
            'paragraph':paragraph,'sentence':3,'basis':'net_income','text':match['epsClause'],
            'paragraphText':match[0],'fiscalYear':fiscal_year,'fiscalQuarter':fiscal_quarter,
            'periodProof':dict(period_proof)}))
    return candidates
