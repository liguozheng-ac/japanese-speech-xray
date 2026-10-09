from pathlib import Path
import re
from speech_xray.reference.manifest import keys, text, sha256
from speech_xray.reference.numeric import integer as json_integer
from speech_xray.corpus.batch_plan import digest
from .serialization import ROOT, private_path


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value):
        raise ValueError('INVALID_EVALUATION_ID')
    return value


def integer(value, name):
    """Accept typed Python integers and existing exact JSON Decimal integers."""
    return value if type(value) is int else json_integer(value,name)


def artifact(value, base, required=True):
    if value is None and not required:return None
    keys(value,('path','sha256'))
    path=(Path(base)/text(value['path'],'artifact path')).resolve()
    if not path.is_relative_to(ROOT.resolve()):raise ValueError('EVALUATION_SOURCE_PATH_ESCAPE')
    sha256(value['sha256'])
    if not path.is_file() or digest(path)!=value['sha256']:raise ValueError('EVALUATION_SOURCE_MISSING_OR_CHANGED')
    return {'path':str(path),'sha256':value['sha256']}


TARGET_FIELDS = ('target_id','target_surface','target_reading','target_mora_span',
                 'target_vowel_class','word_mora_indices','mapping_basis','lexical_identity')


def target(value):
    keys(value,TARGET_FIELDS)
    identifier(value['target_id'])
    for key in ('target_surface','target_reading','lexical_identity'):text(value[key],key)
    indices=value['word_mora_indices']
    if (not isinstance(indices,list) or len(indices)!=2 or any(integer(i,'index')<0 for i in indices)
            or indices[1]!=indices[0]+1 or integer(value['target_mora_span'],'span')!=2
            or value['target_vowel_class'] not in {'A','I','U','E','O'}
            or value['mapping_basis'] not in {'PROLONGED_MARK','KANA_SEQUENCE'}):
        raise ValueError('UNSUPPORTED_LINGUISTIC_TARGET')
    # Reading and position must genuinely yield the declared linguistic candidate.
    from speech_xray.japanese.mora_tokenizer import tokenize_mora
    from speech_xray.japanese.long_vowel_mapper import long_vowel_candidates
    from speech_xray.japanese.reading import normalize_katakana
    tokens=tokenize_mora(value['target_reading'])
    if tokens.issue or normalize_katakana(value['target_reading'])!=value['target_reading']:
        raise ValueError('INVALID_TARGET_READING')
    if not any(list(c.mora_indices)==indices and c.vowel_class==value['target_vowel_class']
               and c.mapping_basis==value['mapping_basis'] for c in long_vowel_candidates(tokens.morae)):
        raise ValueError('TARGET_READING_POSITION_MISMATCH')
    return value
