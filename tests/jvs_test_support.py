"""Self-authored miniature layout and runtime math audio, not JVS corpus content."""

from pathlib import Path
import numpy as np
import soundfile as sf
from corpus_test_support import ROOT,workspace


def tree(directory,speakers=3):
    texts={"VOICEACTRESS100_001":"コーヒーを置きます。","VOICEACTRESS100_002":"空気が流れます。","VOICEACTRESS100_003":"時計を見ます。"}
    for index in range(1,speakers+1):
        folder=directory/f"jvs{index:03}"/"parallel100"
        audio=folder/"wav24kHz16bit";audio.mkdir(parents=True)
        (folder/"transcript_utf8.txt").write_text("".join(f"{key}:{text}\n" for key,text in texts.items()),encoding="utf-8")
        for number,key in enumerate(texts):
            signal=.2*np.sin(2*np.pi*(200+index*10+number)*np.arange(32000)/16000)
            sf.write(audio/(key+".wav"),signal,16000,subtype="PCM_16")
    return directory
