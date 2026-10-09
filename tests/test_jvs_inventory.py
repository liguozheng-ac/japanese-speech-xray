from pathlib import Path
import unittest

from jvs_test_support import ROOT,tree,workspace
from speech_xray.external_jvs.inventory import inventory,speaker_id,prompt_id,transcripts
from speech_xray.corpus.models import SourceType
from speech_xray.corpus.batch_plan import digest
from speech_xray.acoustics.models import evidence_json


class JvsInventoryTests(unittest.TestCase):
    def setUp(self):self.directory=workspace(self);tree(self.directory)
    def scan(self):return inventory(self.directory,source_type=SourceType.TEST_FIXTURE)

    def test_valid_speaker_and_stable_prompt_ids(self):
        for value in ("jvs001","jvs050","jvs100"):self.assertEqual(speaker_id(value),value)
        for value in ("VOICEACTRESS100_001","VOICEACTRESS100_100"):self.assertEqual(prompt_id(value),value)

    def test_invalid_speaker_and_prompt_ids_fail(self):
        for value in ("jvs000","jvs101","jvs1","../jvs001","JVS001"):
            with self.assertRaises(ValueError):speaker_id(value)
        for value in ("VOICEACTRESS100_000","VOICEACTRESS100_101","001",None):
            with self.assertRaises(ValueError):prompt_id(value)

    def test_expected_observed_shared_identity_and_format(self):
        report=self.scan()
        self.assertEqual(report["expected"]["parallel100_wav_count"],10000)
        self.assertEqual(report["observed"],{"speaker_count":3,"parallel100_speaker_count":3,"prompt_count":3,"parallel100_wav_count":9,"shared_prompt_count":3,"five_speaker_prompt_count":0})
        self.assertEqual(report["audio_formats"],{"WAV/PCM_16":9})
        self.assertEqual(report["sample_rates"],{"16000":9})
        self.assertEqual(report["channel_counts"],{"1":9})
        self.assertEqual(len(report["coverage_matrix"]["rows"]),3)

    def test_missing_audio_is_retained_in_matrix(self):
        path=self.directory/"jvs002/parallel100/wav24kHz16bit/VOICEACTRESS100_001.wav"
        path.unlink()
        report=self.scan();row=report["prompts"][0]
        self.assertEqual((row["audio_present_speaker_count"],row["available_speaker_count"]),(2,2))
        self.assertIn("jvs002",row["missing_observed_speaker_ids"])
        self.assertFalse(report["coverage_matrix"]["rows"][0]["speakers"]["jvs002"]["audio_present"])

    def test_unexpected_files_and_invalid_speaker_directory(self):
        (self.directory/"jvs101").mkdir()
        audio=self.directory/"jvs001/parallel100/wav24kHz16bit"
        (audio/"not-a-prompt.wav").write_bytes(b"not corpus audio")
        (self.directory/"outside.wav").write_bytes(b"invalid")
        reasons={item["reason"] for item in self.scan()["unexpected_files"]}
        self.assertTrue({"INVALID_SPEAKER_DIRECTORY","UNEXPECTED_PROMPT_FILENAME","UNEXPECTED_AUDIO_OUTSIDE_SPEAKER_TREE"}<=reasons)

    def test_deterministic_inventory_and_original_hashes(self):
        paths=list(self.directory.rglob("*.wav"));before={str(p):digest(p) for p in paths}
        self.assertEqual(evidence_json(self.scan()),evidence_json(self.scan()))
        self.assertEqual(before,{str(p):digest(p) for p in paths})

    def test_duplicate_hashes_exclude_all_copied_speakers(self):
        base=self.directory/"jvs001/parallel100/wav24kHz16bit/VOICEACTRESS100_001.wav"
        for speaker in ("jvs002","jvs003"):
            (self.directory/speaker/"parallel100/wav24kHz16bit/VOICEACTRESS100_001.wav").write_bytes(base.read_bytes())
        report=self.scan()
        self.assertEqual(report["prompts"][0]["available_speaker_count"],0)
        self.assertEqual(report["duplicate_audio_hashes"][0]["count"],3)

    def test_transcript_conflict_blocks_shared_identity(self):
        path=self.directory/"jvs003/parallel100/transcript_utf8.txt"
        path.write_text(path.read_text(encoding="utf-8").replace("コーヒーを置きます。","コーヒーを飲みます。"),encoding="utf-8")
        row=self.scan()["prompts"][0]
        self.assertEqual(row["transcript_variant_count"],2)
        self.assertIsNone(row["text"])
        self.assertEqual(row["available_speaker_count"],0)

    def test_duplicate_transcript_id_and_malformed_lines(self):
        path=self.directory/"jvs001/parallel100/transcript_utf8.txt"
        path.write_text("VOICEACTRESS100_001:コーヒー\nVOICEACTRESS100_001:ケーキ\nBAD:テスト\nmalformed\n",encoding="utf-8")
        values,issues=transcripts(path,self.directory)
        self.assertFalse(values)
        self.assertEqual(len(issues),3)

    def test_missing_and_ambiguous_official_transcripts(self):
        path=self.directory/"jvs001/parallel100/transcript_utf8.txt";path.unlink()
        first=self.scan();self.assertEqual(first["prompts"][0]["available_speaker_count"],2)
        self.assertEqual(first["transcript_failures"][0]["reason"],"MISSING_OR_AMBIGUOUS_OFFICIAL_TRANSCRIPT")
        source=self.directory/"jvs002/parallel100/transcript_utf8.txt"
        source.with_name("transcripts_utf8.txt").write_bytes(source.read_bytes())
        self.assertEqual(len(self.scan()["transcript_failures"]),2)

    def test_private_paths_reject_tracked_fixture_root(self):
        with self.assertRaises(ValueError):inventory(ROOT/"tests/fixtures")
        with self.assertRaises(ValueError):inventory(ROOT.parent)
        with self.assertRaises(ValueError):transcripts(ROOT/"README.md",self.directory)

    def test_source_cannot_become_controlled_or_claim_readiness(self):
        with self.assertRaises(ValueError):inventory(self.directory,source_type=SourceType.REAL_REFERENCE_RECORDING)
        report=self.scan();self.assertEqual(report["source_type"],"TEST_FIXTURE")
        external=inventory(self.directory)
        self.assertEqual(external["source_type"],"EXTERNAL_RESEARCH_CORPUS")
        self.assertFalse(external["controlled_self_collected_reference_ready"])
        self.assertFalse(external["external_jvs_reference_ready"])

    def test_bad_audio_header_retains_failure_and_excludes_availability(self):
        path=self.directory/"jvs001/parallel100/wav24kHz16bit/VOICEACTRESS100_001.wav"
        path.write_bytes(b"corrupt")
        report=self.scan();self.assertEqual(report["records"][0]["status"],"UNREADABLE_AUDIO_HEADER")
        self.assertEqual(report["prompts"][0]["available_speaker_count"],2)

    def extractor(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location("task007_test_extractor",ROOT/"scripts/extract_jvs_archive.py")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.extract

    def test_archive_extraction_new_private_and_hash_receipt(self):
        import zipfile
        archive=self.directory/"authored-fixture.zip"
        with zipfile.ZipFile(archive,"w") as stream:stream.writestr("fixture/metadata.txt","SELF_AUTHORED_NOT_JVS")
        output=self.directory/"extracted"
        result=self.extractor()(archive,output)
        self.assertEqual(result["archive_sha256"],digest(archive))
        self.assertEqual((output/"fixture/metadata.txt").read_text(),"SELF_AUTHORED_NOT_JVS")
        with self.assertRaises(ValueError):self.extractor()(archive,output)

    def test_archive_traversal_rejected_before_any_extraction(self):
        import zipfile
        archive=self.directory/"traversal-fixture.zip"
        with zipfile.ZipFile(archive,"w") as stream:stream.writestr("../outside.txt","SELF_AUTHORED_REJECTION_TEST")
        output=self.directory/"not-created"
        with self.assertRaises(ValueError):self.extractor()(archive,output)
        self.assertFalse(output.exists())

    def test_archive_cannot_extract_raw_data_into_public_fixture_paths(self):
        import zipfile
        archive=self.directory/"public-rejection-fixture.zip"
        with zipfile.ZipFile(archive,"w") as stream:stream.writestr("not-real-audio.wav",b"TEST_NOT_JVS")
        with self.assertRaises(ValueError):self.extractor()(archive,ROOT/"tests/fixtures/uncreated-jvs")
        self.assertFalse((ROOT/"tests/fixtures/uncreated-jvs").exists())
