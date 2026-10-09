"""Transcript candidates reuse the existing Japanese reading and mora rules."""
from speech_xray.japanese.reading import SudachiReadingProvider
from speech_xray.japanese.mora_tokenizer import tokenize_mora
from speech_xray.japanese.long_vowel_mapper import long_vowel_candidates


def discover_candidates(transcript, provider=None):
    if not isinstance(transcript,str) or not transcript.strip():
        return {'status':'ABSTAIN_UNSUPPORTED_EXTERNAL_SAMPLE','reason_codes':['TRANSCRIPT_MISSING'], 'candidates':[]}
    provider=provider or SudachiReadingProvider()
    pieces=provider.reading_for(transcript).pieces
    if not pieces or ''.join(p.surface for p in pieces)!=transcript:
        return {'status':'ABSTAIN_UNSUPPORTED_EXTERNAL_SAMPLE','reason_codes':['WORD_SEGMENTATION_UNAVAILABLE'],'candidates':[]}
    result=[];unresolved=[];word_index=0
    for piece in pieces:
        if piece.surface in {'。','、','！','？'}:continue
        reading=provider.reading_for(piece.surface)
        if not reading.resolved:
            unresolved.append({'word_index':word_index,'surface':piece.surface,'reason':'NO_READING'})
        else:
            tokens=tokenize_mora(reading.reading)
            if tokens.issue:unresolved.append({'word_index':word_index,'surface':piece.surface,'reason':str(tokens.issue.reason)})
            else:
                for index,c in enumerate(long_vowel_candidates(tokens.morae)):
                    result.append({'status':'POSSIBLE_LONG_VOWEL_TARGET','word_index':word_index,
                        'target_id':f'discovered-w{word_index}-c{index}','target_surface':piece.surface,
                        'target_reading':reading.reading,'target_mora_span':2,'target_vowel_class':str(c.vowel_class),
                        'word_mora_indices':list(c.mora_indices),'mapping_basis':str(c.mapping_basis),
                        'lexical_identity':piece.surface})
        word_index+=1
    return {'status':'CANDIDATES_DISCOVERED' if result else 'NO_LONG_VOWEL_CANDIDATE',
            'reason_codes':[], 'candidates':result,'unresolved_words':unresolved,
            'interpretation':'LINGUISTIC_CANDIDATE_DISCOVERY_NOT_ANNOTATION'}
