from decimal import Decimal
import unittest
from evaluation_test_support import workspace,make_dataset,annotation,evidence,pinned
from speech_xray.evaluation.learner_manifest import load_learner_manifest
from speech_xray.evaluation.annotation import blind_package,begin_annotation,submit_annotation,attach_model_evidence,adjudicate,restore_session
from speech_xray.evaluation.agreement import categorical_agreement
from speech_xray.evaluation.serialization import save,serialize
from speech_xray.evaluation.models import HumanCategory


class BlindAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.root=workspace(self);path,_=make_dataset(self.root/'data')
        self.dataset=load_learner_manifest(path);self.package=blind_package(self.dataset,'authored-obs')
        self.session=begin_annotation(self.package)

    def test_blind_package_has_no_model_or_corpus_label_or_boundaries(self):
        text=serialize(self.package)
        for word in ('mad_distance','ratio_to_median','signed_delta','reference','direction','model_evidence',
                     'SELF_AUTHORED_CORPUS_TAG','target_start_ms','target_end_ms','speaker_native_language'):
            self.assertNotIn(word,text)

    def test_unknown_model_fields_rejected_in_blind_package(self):
        for key in ('mad_distance','model_evidence','corpus_annotation'):
            bad={**self.package,key:1}
            with self.assertRaises(ValueError):begin_annotation(bad)

    def test_nested_model_field_cannot_enter_target(self):
        bad={**self.package,'target':{**self.package['target'],'ratio_to_median':1}}
        with self.assertRaises(ValueError):begin_annotation(bad)

    def test_human_category_does_not_fabricate_boundaries(self):
        session=submit_annotation(self.session,annotation(self.session))
        self.assertEqual(session.state,'ANNOTATED_BLIND')
        record=session.to_dict()['human_annotation'][0]
        self.assertIsNone(record['target_start_ms']);self.assertIsNone(record['target_end_ms'])

    def test_model_attachment_requires_prior_blind_annotation(self):
        ref=save(self.root/'model.json',evidence(self.dataset))
        with self.assertRaisesRegex(ValueError,'PRIMARY_BLIND_ANNOTATION_REQUIRED'):
            attach_model_evidence(self.session,{'path':ref.path,'sha256':ref.sha256})

    def test_primary_annotation_locked_after_attachment(self):
        session=submit_annotation(self.session,annotation(self.session))
        ref=save(self.root/'model.json',evidence(self.dataset))
        session=attach_model_evidence(session,{'path':ref.path,'sha256':ref.sha256})
        self.assertEqual(session.state,'MODEL_EVIDENCE_ATTACHED')
        with self.assertRaises(ValueError):submit_annotation(session,annotation(session,'author-B'))

    def test_wrong_observation_model_evidence_cannot_attach(self):
        session=submit_annotation(self.session,annotation(self.session));value=evidence(self.dataset)
        value['observation_id']='another-obs';ref=save(self.root/'model.json',value)
        with self.assertRaises(ValueError):attach_model_evidence(session,{'path':ref.path,'sha256':ref.sha256})

    def test_disagreement_and_both_original_annotations_preserved(self):
        a=submit_annotation(self.session,annotation(self.session))
        b=submit_annotation(a,annotation(a,'author-B','LONG_VOWEL_REDUCED_OR_ABSENT'))
        self.assertTrue(b.to_dict()['disagreement']);self.assertEqual(len(b.primary_annotations),2)
        c=adjudicate(b,'adjudicator','UNCERTAIN','Listening review',False)
        self.assertEqual(c.primary_annotations,b.primary_annotations)
        self.assertTrue(c.to_dict()['disagreement']);self.assertEqual(c.state,'ADJUDICATED')

    def test_same_annotator_cannot_overwrite_disagreement(self):
        session=submit_annotation(self.session,annotation(self.session))
        with self.assertRaises(ValueError):submit_annotation(session,annotation(session,category='UNCERTAIN'))

    def test_false_blind_attestation_rejected(self):
        record=annotation(self.session);record['blind_attestation']=False
        with self.assertRaises(ValueError):submit_annotation(self.session,record)

    def test_manual_boundaries_require_both_finite_measured_values(self):
        record=annotation(self.session);record.update(target_start_ms=Decimal('100'),target_end_ms=Decimal('240'),boundary_method='MANUAL_ACOUSTIC_REVIEW')
        self.assertEqual(submit_annotation(self.session,record).to_dict()['human_annotation'][0]['target_end_ms'],240)
        for start,end in ((None,Decimal(2)),(Decimal('NaN'),Decimal(2)),(Decimal(2),Decimal(1))):
            bad={**record,'target_start_ms':start,'target_end_ms':end}
            with self.assertRaises(ValueError):submit_annotation(self.session,bad)

    def test_annotations_replay_deterministically(self):
        records=[annotation(self.session,'author-B','UNCERTAIN'),annotation(self.session)]
        first=restore_session(self.package,records);second=restore_session(self.package,list(reversed(records)))
        self.assertEqual(serialize(first.to_dict()),serialize(second.to_dict()))

    def test_human_record_cannot_include_model_field(self):
        record={**annotation(self.session),'mad_distance':Decimal(2)}
        with self.assertRaises(ValueError):submit_annotation(self.session,record)

    def test_agreement_known_counts_and_confusion(self):
        records=[]
        for i,(a,b) in enumerate([('LONG_VOWEL_REALIZED','LONG_VOWEL_REALIZED'),
                                 ('LONG_VOWEL_REDUCED_OR_ABSENT','LONG_VOWEL_REALIZED'),('UNCERTAIN','UNCERTAIN')]):
            for who,cat in [('author-A',a),('author-B',b)]:
                record=annotation(self.session,who,cat,obs='authored-obs-'+str(i));record['annotation_id']+='-'+str(i);records.append(record)
        result=categorical_agreement(records,'author-A','author-B')
        self.assertEqual((result['number_jointly_annotated'],result['exact_agreement_count']),(3,2))
        self.assertEqual(result['confusion_matrix']['LONG_VOWEL_REDUCED_OR_ABSENT']['LONG_VOWEL_REALIZED'],1)
        self.assertTrue(Decimal('.666')<result['exact_agreement_proportion']<Decimal('.667'))

    def test_agreement_zero_pairs_returns_null(self):
        result=categorical_agreement([annotation(self.session)],'author-A','author-B')
        self.assertEqual(result['number_jointly_annotated'],0);self.assertIsNone(result['exact_agreement_proportion'])

    def test_agreement_duplicate_annotation_rejected(self):
        record=annotation(self.session)
        with self.assertRaises(ValueError):categorical_agreement([record,record],'author-A','author-B')
