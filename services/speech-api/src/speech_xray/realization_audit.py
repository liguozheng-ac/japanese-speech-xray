"""Independent private experiment accounting and provenance audit."""
from pathlib import Path
from collections import Counter
from speech_xray.realization_benchmark.artifacts import load, verify, pin
from speech_xray.realization.lexicon import normalized_word
from speech_xray.realization_benchmark.plan import code_pins
from speech_xray.corpus.batch_plan import digest
from speech_xray.realization import Target, Hypotheses, observe, paired_displacements
from speech_xray.alignment.textgrid_parser import parse_textgrid


def non_target_lines(raw, word):
    return b''.join(line for line in raw.splitlines(keepends=True)
        if not line.decode('utf-8-sig').strip() or normalized_word(line.decode('utf-8-sig').split()[0]) != normalized_word(word))


def audit(root, official_dictionary, snapshot):
    root=Path(root);plan=load(root/'experiment-plan.json');summary=load(root/'benchmark-summary.json')
    assert len(plan['bases'])==15 and len(plan['factors'])==12 and len(plan['cases'])==180
    assert len(plan['groups'])==15 and len(plan['conditions'])==3 and int(plan['expected_condition_cases'])==540
    assert plan['code_sha256']==code_pins()
    for key in ('source_plan','source_case_index','capability_audit','inventory'):verify(plan[key])
    original=Path(official_dictionary).read_bytes()
    assert digest(official_dictionary)==plan['configuration']['official_dictionary_sha256']
    for spec in plan['targets'].values():
        h=spec['hypotheses'];assert int(h['target']['mora_span'])==2
        if h['reduced'] is None:continue
        assert [i for i,(a,b) in enumerate(zip(h['canonical'],h['reduced'])) if a!=b]==[int(h['phone_index'])]
        for condition,dictionary in spec['dictionaries'].items():
            raw=verify(dictionary['artifact']).read_bytes();word=h['target']['surface']
            assert non_target_lines(raw,word)==non_target_lines(original,word)
            entries=[l.decode().split() for l in raw.splitlines() if l and normalized_word(l.decode().split()[0])==normalized_word(word)]
            expected=[h['canonical']] if condition=='CANONICAL_ONLY' else [h['reduced']] if condition=='REDUCED_ONLY' else [h['canonical'],h['reduced']]
            assert [e[5:] for e in entries]==expected
            assert all(e[1]=='1.0' for e in entries)
    execution=load(root/'execution-index-resolved.json');receipts={}
    for ref in execution['receipts']:
        receipt=load(verify(ref));key=(receipt['group']['group_id'],receipt['condition']);assert key not in receipts;receipts[key]=receipt
        for artifact in receipt['artifacts']:verify(artifact)
        if receipt['status']=='UNSUPPORTED_REDUCED_HYPOTHESIS':continue
        if receipt['process_returncode']!=0:continue
        spec=plan['targets'][receipt['group']['target_id']]
        expected=spec['hypotheses']['canonical'] if receipt['condition']=='CANONICAL_ONLY' else spec['hypotheses']['reduced']
        expected_set={' '.join(expected)} if receipt['condition']!='COMPETITION_EQUAL_PRIOR' else {' '.join(spec['hypotheses']['canonical']),' '.join(spec['hypotheses']['reduced'])}
        actual=receipt['database_evidence'].get('target_pronunciations',[])
        assert {r['pronunciation'] for r in actual}==expected_set
        assert all(r['probability']==1 and not r['generated_by_rule'] for r in actual)
    assert len(receipts)==45 and sum(int(r['case_count']) for r in receipts.values())==540
    features=load(root/'actual-feature-audit.json')
    assert int(features['effective_align_configuration_count'])==1 and int(features['effective_mfcc_configuration_count'])==1
    models={c['actual_alignment_model_sha256'] for c in features['conditions'].values()}
    assert models=={features['expected_alignment_model_sha256']}
    assert features['configuration_reconciliation']['actual_same_as_frozen_task012'] is True
    for retry in execution['transport_retries']:
        initial=load(verify(retry['initial_attempt']));repeated=load(verify(retry['retry_attempt']))
        assert initial['common_input_signature']==repeated['common_input_signature']
        assert initial['dictionary']==repeated['dictionary']
    for group in plan['groups']:
        rows=[receipts[(group['group_id'],c)] for c in plan['conditions']]
        assert len({r['common_input_signature'] for r in rows})==1
        assert all(r['group']['case_ids']==group['case_ids'] for r in rows)
    case_index=load(root/'case-index.json');assert len(case_index)==180
    rows={ref['case_id']:load(verify(ref['artifact'])) for ref in case_index}
    assert set(rows)=={c['case_id'] for c in plan['cases']}
    counts=Counter()
    for case in plan['cases']:
        for key in ('audio','transcript','task012_result','original_alignment'):verify(case[key])
        row=rows[case['case_id']];h=plan['targets'][case['target_id']]['hypotheses']
        assert row['provenance']['audio']==case['audio'] and row['provenance']['transcript']==case['transcript']
        assert row['target_identity']==h['target']
        assert row['canonical_pronunciation']==h['canonical'] and row['reduced_pronunciation']==h['reduced']
        identity=dict(h['target']);identity['word_index']=int(identity['word_index']);identity['mora_span']=int(identity['mora_span'])
        identity['word_mora_indices']=tuple(int(i) for i in identity['word_mora_indices'])
        hypotheses=Hypotheses(Target(**identity),tuple(h['canonical']),tuple(h['reduced']) if h['reduced'] else None,int(h['phone_index']),h['status'],tuple(h['reasons']))
        group=case['speaker_id']+'__'+case['target_id']
        for condition,field in [('CANONICAL_ONLY','canonical_alignment'),('REDUCED_ONLY','reduced_alignment'),('COMPETITION_EQUAL_PRIOR','competition_alignment')]:
            receipt=receipts[(group,condition)];ref=receipt['grids'].get(case['case_id'])
            if row[field] is not None:
                assert ref is not None and row['provenance']['alignment_sources'][condition]==ref
                assert observe(parse_textgrid(verify(ref)),hypotheses)==row[field]
                stem=receipt['stems'][case['case_id']];raw_score=receipt['database_evidence']['scores'][stem]
                stored=row['alignment_scores'][condition]
                for key in ('num_frames','alignment_log_likelihood','speech_log_likelihood'):assert stored[key]==raw_score[key]
                actual=features['conditions'][group+'__'+condition]['case_features'][case['case_id']]['identity']
                assert stored['feature_sha256']==actual['matrix_sha256']
                assert stored['feature_audit']==pin(root/'actual-feature-audit.json')
        assert paired_displacements(row['canonical_alignment'],row['reduced_alignment'])==row['boundary_displacements']
        selected=row['competition_selected_variant'];counts[selected]+=1
        c=row['competition_alignment']
        if selected=='CANONICAL_SELECTED':assert c['phone_sequence']==h['canonical']
        elif selected=='REDUCED_SELECTED':assert c['phone_sequence']==h['reduced']
        else:assert selected in ('AMBIGUOUS_OR_UNRESOLVED','ALIGNMENT_FAILED')
        old=load(case['task012_result']['path']);gt=old['ground_truth']
        assert row['manipulation_context']['known_sample_count']==gt['actual_perturbed_duration_samples']
        assert row['duration_evidence']['frozen_task012_duration']==old['pipeline']['duration']
        assert row['duration_evidence']['frozen_task010_deviation']==old['pipeline']['deviation']
    expected={'total':180,'canonical':counts['CANONICAL_SELECTED'],'reduced':counts['REDUCED_SELECTED'],
              'ambiguous':counts['AMBIGUOUS_OR_UNRESOLVED'],'failed':counts['ALIGNMENT_FAILED']}
    assert summary['selection_total']==expected
    assert sum(int(v['total']) for v in summary['selection_by_factor'].values())==180
    assert sum(int(v['total']) for v in summary['selection_by_target'].values())==180
    protected=load(snapshot)
    from speech_xray.corpus.validation import PROJECT_ROOT as project
    assert all(digest(project/name)==sha for name,sha in protected['accepted_private_files'].items())
    return {'plan':pin(root/'experiment-plan.json'),'private_integration_pass':True,
            'expected_cases':180,'accounted_condition_cases':540,'condition_runs':45,
            'no_success_filtering':True,'selected_identity_from_exported_sequence':True,
            'official_dictionary_unchanged':True,'non_target_dictionary_bytes_unchanged':True,
            'actual_database_variant_sets_verified':True,'all_reused_source_hashes_verified':True,
            'all_available_geometries_reparsed_from_actual_textgrids':True,
            'database_scores_and_feature_matrix_identities_verified':True,
            'frozen_private_files_verified':len(protected['accepted_private_files']),
            'frozen_duration_and_deviation_evidence_unchanged':True}
