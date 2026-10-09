from dataclasses import replace
import copy
from decimal import Decimal
import unittest
import numpy as np
import soundfile as sf

from corpus_test_support import corpus,digest,load_corpus_manifest,read,session_value,speaker_value,workspace,write
from speech_xray.corpus.audio_validation import inspect_audio
from speech_xray.corpus.intake import validate_corpus
from speech_xray.corpus.models import SourceType
from speech_xray.corpus.speaker_manifest import session_from_json,speaker_from_json


class CorpusIntakeTests(unittest.TestCase):
    def setUp(self):
        self.directory=workspace(self)
        self.path,self.manifest,self.pack=corpus(self.directory)
        self.audio=self.directory/"audio"/(self.manifest.recordings[0].key+".wav")

    def outcome(self,manifest=None):
        return validate_corpus(manifest or self.manifest,self.pack)[0]

    def test_fixture_validates_with_exact_original_metadata_and_hash(self):
        result=self.outcome()
        self.assertEqual(result.status,"VALIDATED")
        self.assertFalse(result.eligible_real_reference)
        self.assertEqual(result.audio_sha256,digest(self.audio))
        self.assertEqual((result.audio.sample_rate_hz,result.audio.channels,result.audio.frame_count),(16000,1,32000))

    def test_pcm16_pcm24_mono_stereo_preserve_original(self):
        for subtype in ("PCM_16","PCM_24"):
            for channels in (1,2):
                signal=np.full((1000,channels),.1)
                sf.write(self.audio,signal,24000,subtype=subtype)
                before=self.audio.read_bytes()
                meta,sha,reason=inspect_audio(self.audio)
                self.assertIsNone(reason)
                self.assertEqual((meta.sample_rate_hz,meta.channels,meta.subtype),(24000,channels,subtype))
                self.assertEqual(self.audio.read_bytes(),before)

    def test_missing_corrupt_and_empty_audio_fail_safely(self):
        self.assertEqual(inspect_audio(self.directory/"missing.wav")[2],"MISSING_OR_UNREADABLE_AUDIO")
        for raw,reason in ((b"", "AUDIO_EMPTY"),(b"not a wav","UNREADABLE_AUDIO")):
            self.audio.write_bytes(raw)
            self.assertEqual(inspect_audio(self.audio)[2],reason)
        sf.write(self.audio,np.array([]),16000,subtype="PCM_16")
        self.assertEqual(inspect_audio(self.audio)[2],"AUDIO_EMPTY")

    def test_digital_silence_and_stereo_cancellation_are_technical(self):
        sf.write(self.audio,np.zeros(1000),16000,subtype="PCM_16")
        self.assertEqual(inspect_audio(self.audio)[2],"DIGITAL_SILENCE")
        signal=np.tile([.125,-.125],(1000,1))
        sf.write(self.audio,signal,16000,subtype="PCM_16")
        self.assertEqual(inspect_audio(self.audio)[2],"MONO_ANALYSIS_DIGITAL_SILENCE")

    def test_very_quiet_nonzero_audio_is_accepted(self):
        sf.write(self.audio,np.full(1000,1/32768),16000,subtype="PCM_16")
        self.assertIsNone(inspect_audio(self.audio)[2])

    def test_low_sample_rate_and_noncanonical_encoding_rejected(self):
        for rate,subtype,reason in ((8000,"PCM_16","SAMPLE_RATE_BELOW_INTAKE_MINIMUM"),(16000,"FLOAT","NONCANONICAL_PCM_ENCODING")):
            sf.write(self.audio,np.full(1000,.1),rate,subtype=subtype)
            self.assertEqual(inspect_audio(self.audio)[2],reason)

    def test_nonfinite_decode_rejected(self):
        sf.write(self.audio,np.array([float("nan"),.1]),16000,subtype="FLOAT")
        self.assertIsNotNone(inspect_audio(self.audio)[2])

    def test_declared_audio_hash_mismatch(self):
        recording=replace(self.manifest.recordings[0],expected_audio_sha256="0"*64)
        self.assertIn("DECLARED_AUDIO_HASH_MISMATCH",self.outcome(replace(self.manifest,recordings=(recording,))).reasons)

    def test_five_copies_reject_all_speaker_ids(self):
        other=self.directory/"copies";other.mkdir()
        _,manifest,pack=corpus(other,5)
        raw=self.audio.read_bytes()
        recordings=[]
        for recording in manifest.recordings:
            from pathlib import Path
            Path(recording.audio_path).write_bytes(raw)
            recordings.append(replace(recording,expected_audio_sha256=digest(self.audio)))
        results=validate_corpus(replace(manifest,recordings=tuple(recordings)),pack)
        self.assertEqual(len(results),5)
        self.assertTrue(all(i.status=="REJECTED_INTAKE" and "DUPLICATE_EXACT_AUDIO_HASH" in i.reasons and not i.eligible_real_reference for i in results))

    def test_duplicate_speaker_prompt_take_rejects_all(self):
        results=validate_corpus(replace(self.manifest,recordings=self.manifest.recordings*2),self.pack)
        self.assertTrue(all("DUPLICATE_SPEAKER_PROMPT_TAKE" in r.reasons for r in results))

    def test_unknown_ids_and_wrong_filename_take(self):
        recording=self.manifest.recordings[0]
        for field,value,reason in (("speaker_id","unknown","UNKNOWN_SPEAKER"),("session_id","unknown","UNKNOWN_OR_CONFLICTING_SESSION"),
                                   ("prompt_id","unknown","UNKNOWN_PROMPT"),("take_id","take-00","INVALID_TAKE_ID")):
            changed=replace(recording,**{field:value})
            self.assertIn(reason,self.outcome(replace(self.manifest,recordings=(changed,))).reasons)
        self.assertIn("NONCANONICAL_PSEUDONYMOUS_FILENAME",self.outcome(replace(self.manifest,recordings=(replace(recording,take_id="take-02"),))).reasons)

    def test_wrong_pack_root_or_session_version_hash_rejected(self):
        self.assertIn("PROMPT_PACK_BINDING_MISMATCH",self.outcome(replace(self.manifest,prompt_pack_version=2)).reasons)
        self.assertIn("PROMPT_PACK_BINDING_MISMATCH",self.outcome(replace(self.manifest,prompt_pack_sha256="0"*64)).reasons)
        session=replace(self.manifest.sessions[0],prompt_pack_version=2)
        self.assertIn("SESSION_PROMPT_PACK_MISMATCH",self.outcome(replace(self.manifest,sessions=(session,))).reasons)

    def test_source_mismatch_synthetic_and_external_cannot_enter_collection(self):
        recording=self.manifest.recordings[0]
        for source,reason in ((SourceType.SYNTHETIC_AUDIO,"SYNTHETIC_AUDIO_NOT_ACCEPTED_FOR_REFERENCE_COLLECTION"),
                               (SourceType.EXTERNAL_RESEARCH_CORPUS,"USE_EXTERNAL_REFERENCE_SET_ADAPTER_NOT_CONTROLLED_COLLECTION")):
            result=self.outcome(replace(self.manifest,recordings=(replace(recording,source_type=source),)))
            self.assertIn(reason,result.reasons)
            self.assertFalse(result.eligible_real_reference)
            self.assertIn("SOURCE_TYPE_MISMATCH",result.reasons)

    def test_real_eligibility_requires_explicit_metadata_in_memory_only(self):
        # Metadata policy assertion only. No real-speaker file/report is created.
        source=SourceType.REAL_REFERENCE_RECORDING
        m=replace(self.manifest,speakers=(replace(self.manifest.speakers[0],source_type=source),),
                  recordings=(replace(self.manifest.recordings[0],source_type=source),))
        self.assertFalse(self.outcome(m).eligible_real_reference)
        speaker=replace(m.speakers[0],self_reported_native_japanese=True,native_status_metadata_status="PARTICIPANT_SUPPLIED")
        session=replace(m.sessions[0],consent_record_id="opaque-consent",consent_metadata_status="PARTICIPANT_SUPPLIED",
                        permission_local_analysis=True,permission_derived_numeric_features=True)
        approved=replace(m,speakers=(speaker,),sessions=(session,))
        self.assertTrue(self.outcome(approved).eligible_real_reference)
        self.assertFalse(session.permission_public_raw_audio)
        for field in ("permission_local_analysis","permission_derived_numeric_features"):
            self.assertFalse(self.outcome(replace(approved,sessions=(replace(session,**{field:False}),))).eligible_real_reference)
        self.assertFalse(self.outcome(replace(approved,speakers=(replace(speaker,self_reported_native_japanese=None),))).eligible_real_reference)

    def test_public_permissions_default_false_and_reject_string_truth(self):
        value=session_value(self.pack)
        value["prompt_pack_version"]=Decimal(value["prompt_pack_version"])
        session=session_from_json(value)
        self.assertFalse(session.permission_public_raw_audio)
        self.assertFalse(session.permission_public_aggregate_statistics)
        value["permission_public_raw_audio"]="true"
        with self.assertRaises(ValueError):session_from_json(value)

    def test_speaker_schema_rejects_extra_personal_fields_and_bool_strings(self):
        value=speaker_value();value["legal_name"]="UNUSED_TEST_FIELD"
        with self.assertRaises(ValueError):speaker_from_json(value)
        value=speaker_value();value["self_reported_native_japanese"]="true"
        with self.assertRaises(ValueError):speaker_from_json(value)

    def test_paths_must_stay_private_and_inside_declared_corpus(self):
        value=read(self.path)
        value["recordings"][0]["audio"]["path"]=str(self.directory.parent/"outside-unread.wav")
        write(self.path,value)
        with self.assertRaises(ValueError):load_corpus_manifest(self.path)
        value["corpus_root"]=str(self.directory.parents[2]/".tools")
        write(self.path,value)
        with self.assertRaises(ValueError):load_corpus_manifest(self.path)

    def test_pinned_metadata_hash_and_duplicate_speaker_manifest(self):
        original=read(self.path)
        changed=copy.deepcopy(original);changed["speaker_manifests"][0]["sha256"]="0"*64;write(self.path,changed)
        with self.assertRaises(ValueError):load_corpus_manifest(self.path)
        original["speaker_manifests"]*=2;write(self.path,original)
        with self.assertRaises(ValueError):load_corpus_manifest(self.path)

    def test_duplicate_keys_nonfinite_json_and_wrong_source_schema(self):
        original=self.path.read_text(encoding="utf-8")
        for value in (original.replace('"schema_version":','"schema_version":"duplicate","schema_version":',1),
                      original.replace('"prompt_pack_version": 1','"prompt_pack_version": NaN',1)):
            self.path.write_text(value,encoding="utf-8")
            with self.assertRaises(ValueError):load_corpus_manifest(self.path)
