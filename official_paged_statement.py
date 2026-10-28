"""Bounded reader for SEC image pages with a matching statement transcript.

The registered layout has a pictured page followed by one white 1pt paragraph,
with paired current/comparative quarterly and annual columns. Unknown layouts
stay pending. This reader never derives a quarter from annual amounts.
"""
import re
from datetime import datetime


TITLE = 'Condensed Consolidated Statements of Operations'
NUMBER = r'\$(?:-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\))'
FOUR = rf'({NUMBER})\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})'
PLAIN = r'(?:-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\))'
PLAIN_FOUR = rf'{PLAIN}\s+{PLAIN}\s+{PLAIN}\s+{PLAIN}'
EPS_PARENT = 'Net income per share attributable to Class A and Class B common stockholders:'
SHARES_PARENT = 'Weighted-average shares used in computing net income per share attributable to Class A and Class B common stockholders:'


def _image(node):
    if node is None or node.tag != 'p' or len(node.xpath('.//img')) != 1:
        return None
    if ''.join(node.itertext()).strip() or len(node.xpath('.//*')) != 1:
        return None
    image=node.xpath('./img')
    if not image:return None
    match=re.fullmatch(r'g[\w]+p(\d+)g1\.jpg',image[0].get('src',''),re.I)
    return (int(match[1]),image[0].get('src')) if match else None


def statement_page(tree, fiscal_year, fiscal_quarter):
    """Return one unambiguous registered page and its explicit period header."""
    if not isinstance(fiscal_year,int) or fiscal_quarter != 4:return None
    possible=[]
    for index,p in enumerate(tree.xpath('//p'),1):
        text=' '.join(' '.join(p.itertext()).split())
        if TITLE.lower() not in text[:120].lower():continue
        possible.append((index,p,text))
    if len(possible) != 1:return None
    index,p,text=possible[0]
    style=re.sub(r'\s+','',p.get('style','')).lower()
    if not re.search(r'(?:^|;)font-size:1pt(?:;|$)',style):return None
    if not re.search(r'(?:^|;)color:#ffffff(?:;|$)',style):return None
    image=_image(p.getprevious())
    if not image or _image(p.getprevious().getprevious()):return None
    page,filename=image
    following=p.getnext()
    if following is None or ''.join(following.itertext()).strip():return None
    if not re.search(r'page-break-before\s*:\s*always',following.get('style',''),re.I):return None
    prefix=re.escape(TITLE)+r' Unaudited \(in millions, except per share amounts\) '
    header=re.match(prefix+r'Three Months Ended Year Ended ([A-Z][a-z]+ \d{1,2}) \1 (20\d{2}) (20\d{2}) \2 \3 (?=Revenue )',text)
    if not header or int(header[3])!=fiscal_year or int(header[2])+1!=fiscal_year:return None
    try:end=datetime.strptime(header[1]+' '+header[3],'%B %d %Y').date().isoformat()
    except ValueError:return None
    if not re.search(r'\s'+str(page)+r'$',text):return None
    revenue=re.match(r'Revenue '+FOUR+r' Costs and expenses:',text[header.end():])
    if not revenue:return None
    body=text[header.end()+revenue.end():].lstrip()
    # Exactly one total is allowed. The registered next row is Cost of revenue;
    # all other revenue labels (with/without punctuation or dollar signs) are
    # unknown competing totals and invalidate this layout.
    other_labels=re.sub(r'^Cost of revenue(?=\s)','',body,count=1)
    if re.search(r'(?i)\brevenues?\b',other_labels):return None
    return {'periodEnd':end,'text':text,'revenueCells':revenue.groups(),
        'statementBody':body,
        'locator':{'layout':'image_page_statement_transcript_v1','page':page,
            'image':filename,'paragraph':index,'column':2,'header':header[0].strip(),
            'columnHeaders':[header[1]+' '+header[2],header[1]+' '+header[3],
                header[1]+' '+header[2]+' (year)',header[1]+' '+header[3]+' (year)']}}


def page_candidates(page, numeric):
    candidates={'epsGaapDiluted':[],'revenue':[]}
    locator=page['locator']
    cells=page['revenueCells']
    value,precision=numeric(cells[1])
    if value>=0:
        candidates['revenue'].append((value*1000000,precision*1000000,
            {**locator,'label':'Revenue','scale':1000000,'rawCells':list(cells)}))
    text=page['text']
    # Anchors must be whole parent labels, not substrings of adjusted/continuing
    # or weighted-share sections. The net-income row immediately precedes EPS.
    # Consume the registered statement rows from the first revenue line. Do
    # not search arbitrary later text where a new annual/adjusted scope can
    # introduce the same EPS labels.
    body_labels=('Cost of revenue','Operations and support (1)','Product development (1)',
        'Sales and marketing (1)','General and administrative (1)','Total costs and expenses',
        'Income from operations','Interest income','Other income (expense), net',
        'Income before income taxes','Provision for income taxes')
    preceding=''.join(re.escape(label)+' '+PLAIN_FOUR+' ' for label in body_labels)
    pattern=(preceding+r'Net income '+FOUR+' '+re.escape(EPS_PARENT)+r' Basic '+FOUR+
        r' Diluted '+FOUR+' '+re.escape(SHARES_PARENT))
    match=re.match(pattern,page['statementBody'])
    if match and text.count(EPS_PARENT)==1 and text.count(SHARES_PARENT)==1:
        cells=match.groups()[8:12]
        value,precision=numeric(cells[1])
        candidates['epsGaapDiluted'].append((value,precision,{**locator,
            'label':'Diluted','parentLabel':EPS_PARENT,'rawCells':list(cells)}))
    return candidates
