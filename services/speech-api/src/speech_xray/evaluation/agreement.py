"""Descriptive paired agreement; no reliability cutoff or diagnostic performance."""
from fractions import Fraction
from .annotation import validate_annotation
from .models import HumanCategory
from speech_xray.reference.numeric import decimal_ratio


def categorical_agreement(records, annotator_a, annotator_b):
    if annotator_a==annotator_b:raise ValueError('TWO_DISTINCT_ANNOTATORS_REQUIRED')
    by_annotator={annotator_a:{},annotator_b:{}}
    for record in records:
        validate_annotation(record)
        who=record['annotator_id']
        if who not in by_annotator:continue
        key=(record['evaluation_run_id'],record['observation_id'],record['blind_package_sha256'])
        if key in by_annotator[who]:raise ValueError('DUPLICATE_AGREEMENT_RECORD')
        by_annotator[who][key]=record['category']
    a,b=by_annotator[annotator_a],by_annotator[annotator_b]
    shared=sorted(set(a)&set(b))
    matrix={x.value:{y.value:0 for y in HumanCategory} for x in HumanCategory}
    for key in shared:matrix[a[key]][b[key]]+=1
    exact=sum(a[key]==b[key] for key in shared)
    return {'annotator_a':annotator_a,'annotator_b':annotator_b,'number_jointly_annotated':len(shared),
        'exact_agreement_count':exact,'exact_agreement_proportion':decimal_ratio(Fraction(exact,len(shared))) if shared else None,
        'confusion_matrix':matrix,'not_jointly_annotated_a':len(set(a)-set(b)),
        'not_jointly_annotated_b':len(set(b)-set(a)), 'interpretation':'DESCRIPTIVE_AGREEMENT_ONLY'}
