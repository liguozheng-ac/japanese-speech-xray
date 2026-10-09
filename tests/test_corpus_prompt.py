import copy
from dataclasses import replace
import unittest

from corpus_test_support import PACK_PATH,ROOT,load_prompt_pack,read,write,workspace
from speech_xray.corpus.prompt_manifest import recording_sheet,validate_prompt_pack


class CorpusPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack=load_prompt_pack(PACK_PATH)
        cls.qa=validate_prompt_pack(cls.pack)

    def test_authored_pack_exact_counts_and_version(self):
        self.assertEqual((self.pack.prompt_pack_version,len(self.pack.prompts),self.qa["target_count"]),(1,24,27))
        self.assertEqual(self.qa["status"],"PASS")
        self.assertFalse(self.qa["authoring_failures"])

    def test_patterns_use_actual_supported_candidates(self):
        self.assertEqual(self.qa["orthographic_pattern_coverage"],{"PROLONGED_MARK":5,"O_U":3,"O_O":3,"E_I":4,"E_E":3,"A_A":3,"I_I":3,"U_U":3})
        self.assertEqual(self.qa["candidate_type_coverage"],{"PROLONGED_MARK":5,"KANA_SEQUENCE":22})

    def test_five_vowel_classes_and_mora_counts(self):
        self.assertEqual(self.qa["vowel_class_coverage"],{"A":4,"E":8,"I":4,"O":7,"U":4})
        self.assertTrue(all(11<=p.expected_mora_count<=17 for p in self.pack.prompts))

    def test_expected_reading_count_and_target_mutations_fail(self):
        p=self.pack.prompts[0];t=p.targets[0]
        variants=[replace(p,expected_reading="ア"),replace(p,expected_mora_count=999),
                  replace(p,targets=(replace(t,surface_hint="存在しない語"),)),
                  replace(p,targets=(replace(t,expected_reading_region="アア"),)),
                  replace(p,targets=(replace(t,expected_vowel_class="A"),)),
                  replace(p,targets=(replace(t,expected_candidate_type="KANA_SEQUENCE"),)),
                  replace(p,text="𠮷。")]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(validate_prompt_pack(replace(self.pack,prompts=(variant,)))["status"],"FAIL")

    def test_duplicate_ids_texts_and_unsupported_schema_fail(self):
        directory=workspace(self);path=directory/"pack.json";original=read(PACK_PATH)
        mutations=[lambda v:v["prompts"].append(v["prompts"][0]),
                   lambda v:v["prompts"][1].update(text=v["prompts"][0]["text"]),
                   lambda v:v["prompts"][0]["targets"].append(v["prompts"][0]["targets"][0]),
                   lambda v:v.update(authorship="EXTERNAL_CORPUS"),lambda v:v.update(prompt_pack_version=0),
                   lambda v:v["prompts"][0]["targets"][0].update(expected_mora_span=3),
                   lambda v:v["prompts"][0]["targets"][0].update(orthographic_pattern="UNKNOWN")]
        for mutation in mutations:
            value=copy.deepcopy(original);mutation(value);write(path,value)
            with self.assertRaises(ValueError):load_prompt_pack(path)

    def test_participant_sheet_has_only_authored_text_ids_filenames(self):
        sheet=recording_sheet(self.pack)
        for term in ("F0","duration","target-01","expected_reading","mora","Hz","ms"):
            self.assertNotIn(term,sheet)
        for p in self.pack.prompts:self.assertIn(p.text,sheet)
        self.assertEqual(sheet,(ROOT/"docs/generated/reference-long-vowel-v1-recording-sheet.md").read_text(encoding="utf-8"))

    def test_checked_in_qa_is_reproducible_and_has_no_acoustic_timing(self):
        self.assertEqual(self.qa,read(ROOT/"docs/generated/reference-long-vowel-v1-prompt-qa.json"))
        self.assertNotIn("start_ms",str(self.qa))
        self.assertNotIn("LongVowelSpan",str(self.qa))
