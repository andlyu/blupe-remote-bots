import concurrent.futures
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from remote_yam.run_assessments import RunAssessments, AssessmentConflict, score_models


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'assessments.sqlite3'
        self.store = RunAssessments(self.path)
        self.store.register('ep_run','runner','user',ended=True)
        self.addCleanup(self.temp.cleanup)

    def label(self, label='Success', revision=0, session='runner', user=None):
        self.store.assess('ep_run',label,revision,session,user)

    def vote(self, session, vote, revision=1):
        self.store.vote('ep_run',revision,vote,session)

    def test_truth_table_and_votes_can_change_remove_and_reinclude(self):
        self.label()
        for correct,incorrect,expected in [(0,0,'included'),(1,0,'included'),(1,1,'included'),(1,2,'excluded'),(2,2,'included')]:
            with self.subTest(correct=correct,incorrect=incorrect):
                for i in range(correct): self.vote('yes'+str(i),1)
                for i in range(incorrect): self.vote('no'+str(i),-1)
                summary=self.store.summaries()['ep_run']
                self.assertEqual((summary['correct'],summary['incorrect'],summary['eligibility']), (correct,incorrect,expected))
                self.assertEqual(summary['label'],'Success')
        self.vote('yes1',-1)
        self.assertEqual(self.store.summaries()['ep_run']['eligibility'],'excluded')
        self.vote('no1',None)
        self.vote('yes1',1)
        self.assertEqual(self.store.summaries()['ep_run']['eligibility'],'included')
        self.vote('no1',None)
        self.assertEqual(self.store.summaries()['ep_run']['incorrect'],1)

    def test_revisions_preserve_old_reviews_and_later_owner_edits(self):
        self.label(); self.vote('reviewer',-1)
        self.label('Failure',1,'different-session','user')
        current=self.store.detail('ep_run','runner')
        self.assertEqual((current['revision'],current['label'],current['correct'],current['incorrect']), (2,'Failure',0,0))
        self.assertEqual(current['history'][1]['incorrect'],1)
        with self.assertRaises(AssessmentConflict): self.vote('reviewer',1,1)
        self.label(None,2)
        self.assertEqual(self.store.summaries()['ep_run']['eligibility'],'unlabeled')
        self.assertEqual(len(self.store.detail('ep_run','runner')['history']),3)
        self.assertTrue(RunAssessments(self.path).detail('ep_run','new','user')['can_edit'])

    def test_wrong_owner_originating_session_and_invalid_payloads(self):
        for session,user in [('other',None),('other','other-user')]:
            with self.assertRaises(PermissionError): self.label(session=session,user=user)
        self.label()
        with self.assertRaises(PermissionError): self.vote('runner',1)
        # The approved review identity is session-based, including the same user
        # on a different session. Only the originating session is disallowed.
        self.vote('other-session',1)
        with self.assertRaises(AssessmentConflict): self.label('Failure',0)
        with self.assertRaises(ValueError): self.vote('bad',True)
        with self.assertRaises(ValueError): self.label('policy_complete',1)
        self.store.register('ep_run','hijacker','impostor',ended=True)
        self.assertFalse(self.store.detail('ep_run','hijacker','impostor')['can_edit'])

    def test_duplicate_writes_and_concurrent_votes_are_one_per_session(self):
        self.label();self.label()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: self.vote('reviewer',1),range(12)))
        summary=self.store.summaries()['ep_run']
        self.assertEqual((summary['revision'],summary['correct']),(1,1))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assessment_vote_events').fetchone()[0],1)

    def test_live_is_provisional_and_machine_outcomes_never_supply_labels(self):
        self.store.register('ep_live','runner',ended=False)
        self.store.assess('ep_live','Failure',0,'runner')
        live=self.store.summaries()['ep_live']
        self.assertEqual(live['eligibility'],'provisional')
        with self.assertRaises(ValueError): self.store.vote('ep_live',1,1,'other')
        scores=score_models([{'model':'M','assessment':live},{'model':'M','result':'Success','outcome':'policy_complete'}])
        self.assertEqual((scores[0]['denominator'],scores[0]['unlabeled'],scores[0]['provisional'],scores[0]['rate']), (0,1,1,None))
        self.store.register('ep_live','runner',ended=True)
        self.assertEqual(self.store.summaries()['ep_live']['eligibility'],'included')

    def test_complete_filtered_dataset_versions_and_public_projection(self):
        self.label();self.vote('r',-1)
        rows=[{'model':'M','assessment':self.store.summaries()['ep_run']},
              {'model':'M','model_version':'v2','assessment':RunAssessments.summary({'label':'Success'})}]
        rows += [{'model':'M','model_version':'v2','assessment':RunAssessments.summary({'label':'Failure'})} for _ in range(200)]
        rows += [{'model':None,'result':'Success'}]
        scores=score_models(rows)
        self.assertEqual(scores[-1]['denominator'],201)
        self.assertEqual(scores[-1]['successes'],1)
        public=json.dumps(self.store.detail('ep_run','other'))
        for value in ['owner_session','owner_user','author_session','reviewer','runner']:
            self.assertNotIn(value,public)

    def test_hollow_categories_omit_both_counts_and_vote_changes_restore_original_label(self):
        self.label()
        self.store.register('ep_failure','runner',ended=True)
        self.store.assess('ep_failure','Failure',0,'runner')
        self.store.register('ep_unlabeled','runner',ended=True)
        def scores():
            return score_models([{'model':'M','assessment':summary}
                                 for summary in self.store.summaries().values()])[0]
        self.assertEqual((scores()['successes'],scores()['failures'],scores()['denominator']),(1,1,2))
        self.vote('reviewer',-1)
        self.store.vote('ep_failure',1,-1,'reviewer')
        score=scores()
        self.assertEqual((score['successes'],score['failures'],score['denominator'],score['rate']),(0,0,0,None))
        self.assertEqual((score['excluded'],score['unlabeled']),(2,1))
        self.vote('tie',1)
        self.store.vote('ep_failure',1,None,'reviewer')
        self.assertEqual((scores()['successes'],scores()['failures'],scores()['denominator']),(1,1,2))
        self.assertEqual(self.store.summaries()['ep_run']['label'],'Success')
        self.assertEqual(self.store.detail('ep_failure','other')['history'][0]['label'],'Failure')
