import unittest
from quarterly_policy import merge_manifest_record


class ReviewedQuarterAssociationTests(unittest.TestCase):
    def test_keurig_wrong_quarter_values_are_corrected_only_with_exact_sources(self):
        import copy
        base='https://www.sec.gov/Archives/edgar/data/1418135/'
        wrong=base+'000141813526000048/ex991-keurigdrpepperreport.htm'
        filing=base+'000141813526000026/kdp-20260331.htm'
        release=base+'000141813526000020/ex991-keurigdrpepperreport.htm'
        for quarter,date in ((2,'2026-08-06'),(1,'2026-04-23')):
            with self.subTest(priorQuarter=quarter):
                old=dict(ticker='KDP',periodEnd='2026-03-31',fiscalYear=2026,fiscalQuarter=quarter,date=date,
                    verifiedAt='2026-10-28',epsGaapDiluted=0.04,revenue=7309000000,
                    releaseSourceUrl=wrong if quarter==2 else release,epsSourceUrl=wrong,revenueSourceUrl=wrong,
                    epsVerificationStatus='conflict',revenueVerificationStatus='conflict')
                new=dict(ticker='KDP',periodEnd='2026-03-31',fiscalYear=2026,fiscalQuarter=1,date='2026-04-23',
                    verifiedAt='2026-10-28',epsGaapDiluted=0.20,revenue=3976000000,
                    releaseSourceUrl=release,secUrl=filing,epsSourceUrl=filing,revenueSourceUrl=filing,
                    epsVerificationStatus='verified',revenueVerificationStatus='verified')
                result=merge_manifest_record(old,new)
                self.assertEqual((result['epsGaapDiluted'],result['revenue']),(0.20,3976000000))
                self.assertEqual((result['epsVerificationStatus'],result['revenueVerificationStatus']),('verified','verified'))
                self.assertEqual(result['metricCorrectionEvidence']['revenue']['oldSourceUrl'],wrong)
                self.assertEqual(result['metricCorrectionEvidence']['revenue']['newSourceUrl'],filing)
                self.assertEqual(merge_manifest_record(result,new)['metricCorrectionEvidence'],result['metricCorrectionEvidence'])
                unknown=copy.deepcopy(old);unknown['metricConflicts']={'revenue':[{'value':123,'sourceUrl':'https://unknown.test'}]}
                self.assertEqual(merge_manifest_record(unknown,new)['revenueVerificationStatus'],'conflict')
                other=copy.deepcopy(new);other['revenueSourceUrl']=filing+'?different'
                self.assertEqual(merge_manifest_record(old,other)['revenueVerificationStatus'],'conflict')

    def test_pentair_preliminary_event_date_does_not_replace_final_release(self):
        base='https://www.sec.gov/Archives/edgar/data/77360/'
        old=dict(ticker='PNR',periodEnd='2026-06-30',fiscalYear=2026,fiscalQuarter=2,date='2026-07-10',
            verifiedAt='2026-10-28',releaseSourceUrl=base+'000007736026000039/july2026pre-earningsexhibit.htm')
        new={**old,'date':'2026-07-28','releaseSourceUrl':base+'000007736026000042/q22026pressrelease.htm'}
        row=merge_manifest_record(old,new)
        self.assertEqual(row['date'],'2026-07-28')
        self.assertEqual(row['releaseCorrectionEvidence']['oldDate'],'2026-07-10')
        self.assertEqual(row['releaseCorrectionEvidence']['newSourceUrl'],new['releaseSourceUrl'])
        self.assertEqual(merge_manifest_record(row,new)['releaseCorrectionEvidence'],row['releaseCorrectionEvidence'])


class MetricRevisionTests(unittest.TestCase):
    def test_gross_and_net_interest_revenue_require_same_filing_and_definition(self):
        from official_sources import parse_inline_quarter
        from test_official_real_documents import document,SOURCES
        filing=SOURCES['AMP-Q2']['filing']['url']
        facts='https://data.sec.gov/api/xbrl/companyfacts/CIK0000820027.json'
        parsed=parse_inline_quarter(document('AMP-Q2','filing'),'2026-06-30',cik='820027')
        evidence=[{'value':value,'sourceUrl':facts,'locator':{'tag':tag,
            'accession':'0000820027-26-000043','periodStart':'2026-04-01','periodEnd':'2026-06-30','unit':'USD'}}
            for tag,value in [('Revenues',5013000000),('RevenuesNetOfInterestExpense',4940000000)]]
        old={**self.original(),**parsed,'ticker':'AMP','revenue':None,'revenueVerificationStatus':'conflict',
             'secUrl':filing,'accessionNumber':'0000820027-26-000043','revenueSourceUrl':filing,
             'epsSourceUrl':filing,'releaseSourceUrl':'https://www.sec.gov/Archives/edgar/data/820027/000082002726000038/q22026er.htm',
             'metricConflicts':{'revenue':evidence}}
        new={**old,**parsed,'verifiedAt':'2026-10-28','revenueVerificationStatus':'verified','metricConflicts':{}}
        new['metricDefinitionEvidence']['revenue']['sourceUrl']=filing
        row=merge_manifest_record(old,new)
        self.assertEqual(row['revenueVerificationStatus'],'verified')
        self.assertEqual(row['revenue'],4940000000)
        self.assertEqual(row['metricConflictResolutionEvidence']['revenue']['previousEvidence'],evidence)
        different_accession={**new,'accessionNumber':'0000820027-26-000099'}
        self.assertEqual(merge_manifest_record(old,different_accession)['revenueVerificationStatus'],'conflict')
        unknown={**old,'metricConflicts':{'revenue':evidence+[{'value':1,'sourceUrl':facts,'locator':{'tag':'OtherRevenue'}}]}}
        self.assertEqual(merge_manifest_record(unknown,new)['revenueVerificationStatus'],'conflict')

    def test_joint_venture_conflict_resolution_requires_original_table_evidence(self):
        release='https://www.sec.gov/Archives/edgar/data/1063761/000110465926093361/tm2620726d2_ex99-1.htm'
        evidence=[{'value':1790598000,'sourceUrl':release,'locator':{'table':8,'label':'Total revenue'}},
                  {'value':1041361000,'sourceUrl':release,'locator':{'table':12,'label':'Total revenue'}}]
        old={**self.original(),'ticker':'SPG','secUrl':None,'releaseSourceUrl':release,
             'metricSourceUrl':release,'revenueSourceUrl':release,'revenue':None,
             'revenueVerificationStatus':'conflict','metricConflicts':{'revenue':evidence}}
        new={**old,'verifiedAt':'2026-10-28','revenue':1790598000,'revenueVerificationStatus':'verified',
             'metricConflicts':{},'metricExclusionEvidence':[{'sourceUrl':release,'table':12,
             'reason':'nonconsolidated_statement','heading':'Unaudited Joint Venture Combined Statements of Operations'}]}
        row=merge_manifest_record(old,new)
        self.assertEqual(row['revenueVerificationStatus'],'verified')
        self.assertEqual(row['metricConflictResolutionEvidence']['revenue']['previousEvidence'],evidence)
        no_proof={k:v for k,v in new.items() if k!='metricExclusionEvidence'}
        self.assertEqual(merge_manifest_record(old,no_proof)['revenueVerificationStatus'],'conflict')
        extra={**old,'metricConflicts':{'revenue':evidence+[{'value':99,'sourceUrl':release,'locator':{'table':13}}]}}
        self.assertEqual(merge_manifest_record(extra,new)['revenueVerificationStatus'],'conflict')

    def test_non_gaap_only_conflict_can_be_resolved_with_same_actual_and_evidence(self):
        filing='https://www.sec.gov/Archives/edgar/data/1800/000162828026050134/abt-20260630.htm'
        release='https://www.sec.gov/Archives/edgar/data/1800/000162828026048377/abt-2026q2xexhibitx991.htm'
        evidence=[{'value':0.53,'sourceUrl':filing},{'value':1.31,'sourceUrl':release,
            'locator':{'label':'Diluted Earnings per Common Share, excluding Specified Items, as described below'}}]
        old={**self.original(),'ticker':'ABT','secUrl':filing,'accessionNumber':'0001628280-26-050134',
             'releaseSourceUrl':release,'epsSourceUrl':filing,'epsGaapDiluted':0.53,
             'epsVerificationStatus':'conflict','metricConflicts':{'epsGaapDiluted':evidence}}
        new={**old,'verifiedAt':'2026-10-28','epsVerificationStatus':'verified','metricConflicts':{}}
        row=merge_manifest_record(old,new)
        self.assertEqual(row['epsVerificationStatus'],'verified')
        self.assertEqual(row['metricConflictResolutionEvidence']['epsGaapDiluted']['previousEvidence'],evidence)
        unknown={**old,'metricConflicts':{'epsGaapDiluted':evidence+[{'value':0.65,'sourceUrl':filing}]}}
        self.assertEqual(merge_manifest_record(unknown,new)['epsVerificationStatus'],'conflict')
        different={**new,'epsGaapDiluted':0.54}
        self.assertEqual(merge_manifest_record(old,different)['epsVerificationStatus'],'conflict')
        no_previous_value={**old,'epsGaapDiluted':None}
        from_release={**new,'epsSourceUrl':release}
        self.assertEqual(merge_manifest_record(no_previous_value,from_release)['epsVerificationStatus'],'verified')

    def test_same_filing_rounded_statement_preserves_precise_verified_value(self):
        filing='https://www.sec.gov/Archives/edgar/data/1375365/000137536526000014/smci-20260331.htm'
        old={**self.original(),'ticker':'SMCI','secUrl':filing,'accessionNumber':'0001375365-26-000014',
             'revenue':10243014000,'revenueVerificationStatus':'verified'}
        new={**old,'verifiedAt':'2026-10-28','revenue':10243000000,'revenueSourceUrl':filing,
             'metricLocators':{'revenue':{'table':47,'row':4,'column':5,'label':'Net sales','precision':'100000'}}}
        row=merge_manifest_record(old,new)
        self.assertEqual(row['revenue'],10243014000)
        self.assertEqual(row['revenueVerificationStatus'],'verified')
        self.assertEqual(row['revenueSourceUrl'],old['revenueSourceUrl'])
        self.assertEqual(row['metricPrecisionEvidence']['revenue'][0]['roundedValue'],10243000000)
        repeated=merge_manifest_record(row,new)
        self.assertEqual(repeated['metricPrecisionEvidence'],row['metricPrecisionEvidence'])
        other={**new,'secUrl':filing.replace('000014','000099'),'accessionNumber':'0001375365-26-000099'}
        self.assertEqual(merge_manifest_record(old,other)['revenueVerificationStatus'],'conflict')
        outside={**new,'revenue':10242900000}
        self.assertEqual(merge_manifest_record(old,outside)['revenueVerificationStatus'],'conflict')

    def test_reviewed_ea_guidance_conflict_resolution_keeps_evidence(self):
        filing='https://www.sec.gov/Archives/edgar/data/712515/000071251525000030/ea-20250630.htm'
        exhibit='https://www.sec.gov/Archives/edgar/data/712515/000071251525000027/earningspressrelease2025_0.htm'
        evidence=[{'value':0.79,'sourceUrl':filing},
                  {'value':0.58,'sourceUrl':exhibit,'locator':{'table':7,'row':35,'column':4,'label':'Diluted'}}]
        old={**self.original(),'ticker':'EA','periodEnd':'2025-06-30','epsGaapDiluted':0.79,
             'epsSourceUrl':filing,'epsVerificationStatus':'conflict', 'metricConflicts':{'epsGaapDiluted':evidence}}
        new={**old,'verifiedAt':'2026-10-28','epsVerificationStatus':'verified','metricConflicts':{}}
        resolved=merge_manifest_record(old,new)
        self.assertEqual(resolved['epsVerificationStatus'],'verified')
        self.assertEqual(resolved['metricConflictResolutionEvidence']['epsGaapDiluted']['previousEvidence'],evidence)
        unknown={**old,'metricConflicts':{'epsGaapDiluted':evidence+[{'value':0.65,'sourceUrl':exhibit}]}}
        self.assertEqual(merge_manifest_record(unknown,new)['epsVerificationStatus'],'conflict')

    def test_reviewed_schwab_fiscal_year_correction_retains_comparison_evidence(self):
        source='https://www.sec.gov/Archives/edgar/data/316709/000031670926000035/a3q26exhibit991.htm'
        old={**self.original(),'ticker':'SCHW','periodEnd':'2026-09-30','date':'2026-10-15',
             'fiscalYear':2025,'fiscalQuarter':3,'releaseSourceUrl':source}
        new={**old,'fiscalYear':2026,'verifiedAt':'2026-10-27'}
        corrected=merge_manifest_record(old,{k:v for k,v in new.items() if k!='ticker'})
        self.assertEqual((corrected['fiscalYear'],corrected['fiscalQuarter']),(2026,3))
        self.assertEqual(corrected['fiscalIdentityCorrectionEvidence']['oldFiscalYear'],2025)
        self.assertEqual(corrected['fiscalIdentityCorrectionEvidence']['releaseSourceUrl'],source)
        self.assertEqual(merge_manifest_record(corrected,new)['fiscalIdentityCorrectionEvidence'],
                         corrected['fiscalIdentityCorrectionEvidence'])

    def test_reviewed_broadridge_earnings_date_overrides_earlier_board_event(self):
        from datetime import date
        from verified_history import apply_official_records
        source='https://www.sec.gov/Archives/edgar/data/1383312/000138331225000024/br-20250804.htm'
        old={**self.original(),'ticker':'BR','periodEnd':'2025-06-30',
             'date':'2025-08-04','releaseSourceUrl':source}
        new={**old,'date':'2025-08-05','verifiedAt':'2026-10-27'}
        corrected=merge_manifest_record(old,{k:v for k,v in new.items() if k!='ticker'})
        self.assertEqual(corrected['date'],'2025-08-05')
        self.assertEqual(corrected['releaseCorrectionEvidence']['oldDate'],'2025-08-04')
        self.assertEqual(corrected['releaseCorrectionEvidence']['newSourceUrl'],source)
        self.assertEqual(merge_manifest_record(corrected,new)['releaseCorrectionEvidence'],
                         corrected['releaseCorrectionEvidence'])
        old={**old,'periodScope':'quarter','fiscalYear':2025,'fiscalQuarter':4,'currency':'USD'}
        reviewed=merge_manifest_record(old,{**old,'date':'2025-08-05','verifiedAt':'2026-10-27'})
        history,_=apply_official_records([{'ticker':'BR'}],{'BR':[]},[old],date(2026,10,27))
        history,_=apply_official_records([{'ticker':'BR'}],history,[reviewed],date(2026,10,27))
        self.assertEqual(history['BR'][0]['date'],'2025-08-05')
        self.assertEqual(history['BR'][0]['releaseCorrectionEvidence']['oldDate'],'2025-08-04')

    def test_reviewed_amcor_release_date_correction_retains_old_evidence_on_repeat(self):
        base='https://www.sec.gov/Archives/edgar/data/1748790/'
        old={**self.original(),'ticker':'AMCR','periodEnd':'2025-12-31',
             'date':'2026-05-06','releaseSourceUrl':base+'000174879026000014/amcr-20260506.htm'}
        new={**old,'date':'2026-02-03','verifiedAt':'2026-10-26',
             'releaseSourceUrl':base+'000174879026000004/amcr-20260203.htm'}
        corrected=merge_manifest_record(old,{k:v for k,v in new.items() if k!='ticker'})
        self.assertEqual(corrected['date'],'2026-02-03')
        self.assertEqual(corrected['releaseCorrectionEvidence']['oldDate'],'2026-05-06')
        self.assertEqual(corrected['releaseCorrectionEvidence']['oldSourceUrl'],old['releaseSourceUrl'])
        self.assertEqual(corrected['releaseCorrectionEvidence']['newSourceUrl'],new['releaseSourceUrl'])
        self.assertEqual(merge_manifest_record(corrected,new)['releaseCorrectionEvidence'],
                         corrected['releaseCorrectionEvidence'])

    def test_reviewed_msci_share_count_is_corrected_only_for_exact_source_and_locator(self):
        from official_metrics import parse_statement_metrics
        from test_official_real_documents import document,SOURCES
        s=SOURCES['MSCI'];source=s['exhibit']['url']
        old={**self.original(),'ticker':'MSCI','periodEnd':'2025-12-31','epsGaapDiluted':74697,
             'epsSourceUrl':source,'metricLocators':{'epsGaapDiluted':{'label':'Diluted','precision':'1','table':7,'row':43,'column':7}}}
        parsed=parse_statement_metrics(document('MSCI','exhibit'),s['periodEnd'],currency='USD',
            fiscal_year=s['fiscalYear'],fiscal_quarter=s['fiscalQuarter'])
        new={**old,**parsed,'verifiedAt':'2026-10-26','epsSourceUrl':source}
        corrected=merge_manifest_record(old,{k:v for k,v in new.items() if k!='ticker'})
        self.assertEqual(corrected['epsGaapDiluted'],3.81)
        self.assertEqual(corrected['epsVerificationStatus'],'verified')
        self.assertEqual(corrected['metricCorrectionEvidence']['epsGaapDiluted']['oldValue'],74697)
        self.assertEqual(corrected['metricCorrectionEvidence']['epsGaapDiluted']['newLocator']['label'],
            'Earnings per diluted common share')
        self.assertEqual(merge_manifest_record(corrected,new)['epsGaapDiluted'],3.81)
        wrong_source={**new,'epsSourceUrl':'https://example.invalid/unreviewed'}
        self.assertEqual(merge_manifest_record(old,wrong_source)['epsVerificationStatus'],'conflict')

    def test_four_reviewed_rsg_gross_values_are_corrected_to_official_net_revenue(self):
        pairs=[
            ('2026-06-30',5076000000,4430000000,'000106039126000275/rsg-20260630.htm','000106039126000273/exhibit991q22026.htm'),
            ('2025-09-30',4827000000,4212000000,'000162828025047655/rsg-20250930.htm','000162828025047534/exhibit991q32025.htm'),
            ('2025-06-30',4882000000,4235000000,'000106039125000216/rsg-20250630.htm','000106039125000215/exhibit991q22025.htm'),
            ('2025-03-31',4593000000,4009000000,'000106039125000170/rsg-20250331.htm','000106039125000169/exhibit991q12025.htm')]
        prefix='https://www.sec.gov/Archives/edgar/data/1060391/'
        for period,old_value,new_value,filing,release in pairs:
            with self.subTest(period=period):
                old={**self.original(),'ticker':'RSG','periodEnd':period,'revenue':old_value,
                     'revenueSourceUrl':prefix+filing}
                new={**old,'verifiedAt':'2026-10-26','revenue':new_value,
                     'revenueSourceUrl':prefix+release}
                corrected=merge_manifest_record(old,new)
                self.assertEqual(corrected['revenue'],new_value)
                self.assertEqual(corrected['revenueVerificationStatus'],'verified')
                self.assertEqual(corrected['metricCorrectionEvidence']['revenue']['oldValue'],old_value)
                self.assertEqual(corrected['metricCorrectionEvidence']['revenue']['newSourceUrl'],prefix+release)
                parsed_without_ticker={k:v for k,v in new.items() if k!='ticker'}
                self.assertEqual(merge_manifest_record(old,parsed_without_ticker)['revenue'],new_value)
                repeated=merge_manifest_record(corrected,new)
                self.assertEqual(repeated['revenue'],new_value)
                self.assertEqual(repeated['metricCorrectionEvidence'],corrected['metricCorrectionEvidence'])
                wrong_source={**new,'revenueSourceUrl':prefix+'unreviewed.htm'}
                self.assertEqual(merge_manifest_record(old,wrong_source)['revenueVerificationStatus'],'conflict')

    def original(self):
        return {'ticker': 'ABC', 'periodEnd': '2026-06-30', 'date': '2026-07-20',
                'verifiedAt': '2026-10-22', 'epsGaapDiluted': 1.41, 'revenue': 2322000000,
                'epsBasis': 'GAAP diluted', 'releaseSourceUrl': 'https://example.invalid/original',
                'metricSourceUrl': 'https://example.invalid/statement',
                'epsSourceUrl': 'https://example.invalid/statement',
                'revenueSourceUrl': 'https://example.invalid/statement'}

    def test_later_different_official_value_is_a_conflict_without_explicit_revision(self):
        old = self.original()
        new = {**old, 'verifiedAt': '2026-10-24', 'epsGaapDiluted': 2,
               'epsSourceUrl': 'https://example.invalid/later-comparative'}
        result = merge_manifest_record(old, new)
        self.assertEqual(result['epsGaapDiluted'], 1.41)
        self.assertEqual(result.get('epsVerificationStatus'), 'conflict')
        self.assertEqual(result['metricConflicts']['epsGaapDiluted'][1]['value'], 2)
        self.assertEqual(result['revenue'], 2322000000)

    def test_confirmed_partial_restatement_updates_only_that_field_and_keeps_original_release(self):
        old = self.original()
        new = {**old, 'verifiedAt': '2026-10-24', 'date': '2026-10-23',
               'epsGaapDiluted': 1.5, 'revenue': None,
               'epsSourceUrl': 'https://example.invalid/correction',
               'metricRevision': {'epsGaapDiluted': '2026-10-23'}}
        result = merge_manifest_record(old, new)
        self.assertEqual(result['epsGaapDiluted'], 1.5)
        self.assertEqual(result['revenue'], 2322000000)
        self.assertEqual(result['revenueSourceUrl'], old['revenueSourceUrl'])
        self.assertEqual(result['date'], '2026-07-20')

    def test_older_comparative_cannot_reverse_a_confirmed_restatement(self):
        revised = {**self.original(), 'epsGaapDiluted': 1.5,
                   'metricRevision': {'epsGaapDiluted': '2026-10-23'}}
        repeated = {**self.original(), 'verifiedAt': '2026-10-24'}
        result = merge_manifest_record(revised, repeated)
        self.assertEqual(result['epsGaapDiluted'], 1.5)
        self.assertNotEqual(result.get('epsVerificationStatus'), 'conflict')

    def test_rechecking_one_source_does_not_silently_clear_an_unresolved_conflict(self):
        old = self.original()
        conflict = merge_manifest_record(old, {**old, 'epsGaapDiluted': 2})
        result = merge_manifest_record(conflict, old)
        self.assertEqual(result.get('epsVerificationStatus'), 'conflict')


if __name__ == '__main__':
    unittest.main()
