import importlib.metadata as metadata
import json
import sys
import spacy
import sudachipy
import sudachidict_core
from sudachipy import dictionary, tokenizer
instance = dictionary.Dictionary(dict='core').create()
print(json.dumps({
    'executable': sys.executable,
    'versions': {name: metadata.version(name) for name in ['spacy', 'SudachiPy', 'SudachiDict-core']},
    'tokens': [{'surface': part.surface(), 'reading': part.reading_form()}
               for part in instance.tokenize('今日はコーヒーを飲みました。', tokenizer.Tokenizer.SplitMode.B)],
}, ensure_ascii=False))
