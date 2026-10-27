import unittest
from quarterly_policy import merge_manifest_record


class MetricRevisionTests(unittest.TestCase):
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
