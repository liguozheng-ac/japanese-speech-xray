"""Isolated, structured MFA argv using the accepted CPU configuration."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import zipfile
from speech_xray.realization import derive_hypotheses, override_lexicon
from speech_xray.realization.models import Target
from .resources import verify
from .errors import ProductError
from .diagnostics import retain_alignment_failure


def no_alignments_reported(log_path):
    """Recognize the pinned MFA terminal exception, not generic nonzero exits."""
    try:
        with log_path.open('rb') as log:
            log.seek(0, 2)
            log.seek(max(0, log.tell() - 16384))
            tail = log.read(16384).decode('utf-8', errors='replace')
    except OSError:
        return False
    # An ordinary mention of the exception or a traceback source line is insufficient.
    return re.search(r'^montreal_forced_aligner\.exceptions\.NoAlignmentsError: NoAlignmentsError:\s*$',
                     tail, re.MULTILINE) is not None


class MFARuntime:
    def __init__(self, settings):
        self.settings = settings
        for resource in settings.runtime_resources:
            verify(resource)
        for resource in (settings.acoustic_model, settings.dictionary, settings.g2p_model):
            if resource is None:
                raise ValueError('ALIGNMENT_RESOURCES_NOT_CONFIGURED')
            verify(resource)
        if not settings.micromamba.is_file() or not (settings.mfa_environment / 'Scripts/mfa.exe').is_file():
            raise ValueError('ALIGNMENT_RUNTIME_UNAVAILABLE')
        records = [json.loads(p.read_text()) for p in (settings.mfa_environment / 'conda-meta').glob('montreal-forced-aligner-*.json')]
        if len(records) != 1 or records[0]['version'] != settings.mfa_version:
            raise ValueError('ALIGNMENT_ENGINE_VERSION_CHANGED')
        with zipfile.ZipFile(settings.acoustic_model.path) as archive:
            meta = json.loads(archive.read('japanese_mfa/meta.json'))
        self.inventory = tuple(meta['phones'])
        groups = meta['phone_groups']
        self.pairs = tuple((long, long[:-1]) for long in self.inventory if long.endswith('ː')
            and any(long in group and long[:-1] in group for group in groups.values()))
        self.dictionary_bytes = settings.dictionary.path.read_bytes()

    def hypotheses(self, binding, word_index):
        target = Target(binding.target_id, binding.surface, binding.reading, word_index,
                        binding.local_mora_indices, binding.vowel_class, binding.mapping_basis)
        return derive_hypotheses(target, binding.canonical, binding.phone_index, self.inventory, self.pairs)

    def align(self, audio_path, binding, folder, hypotheses=None):
        settings = self.settings
        for resource in settings.runtime_resources:
            verify(resource)
        for resource in (settings.acoustic_model, settings.dictionary, settings.g2p_model):
            verify(resource)
        folder.mkdir()
        source = folder / 'input'; source.mkdir()
        shutil.copyfile(audio_path, source / 'item000.wav')
        (source / 'item000.lab').write_bytes((binding.prompt.display_text + '\n').encode('utf-8'))
        dictionary = settings.dictionary.path
        if hypotheses is not None:
            overridden, _ = override_lexicon(self.dictionary_bytes, hypotheses,
                                            'COMPETITION_EQUAL_PRIOR', binding.silence_fields)
            dictionary = folder / 'competition.dict'; dictionary.write_bytes(overridden)
        env = os.environ.copy()
        # Names/models are explicit paths, while each request owns all mutable MFA state.
        home = folder / 'home'; home.mkdir()
        env.update({'MFA_ROOT_DIR': str(folder / 'mfa-root'), 'USERPROFILE': str(home),
                    'HOME': str(home), 'TEMP': str(folder / 'temp'), 'TMP': str(folder / 'temp')})
        (folder / 'temp').mkdir()
        argv = [str(settings.micromamba), '--no-rc', 'run', '-p', str(settings.mfa_environment),
                str(settings.mfa_environment / 'Scripts/mfa.exe'), 'align', str(source), str(dictionary),
                str(settings.acoustic_model.path), str(folder / 'aligned'), '--g2p_model_path',
                str(settings.g2p_model.path), '--temporary_directory', str(folder / 'mfa-temp'),
                '--single_speaker', '--num_jobs', '1', '--no_use_postgres', '--clean']
        try:
            with (folder / 'alignment.log').open('wb') as log:
                completed = subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        except OSError as error:
            retain_alignment_failure(settings, folder, audio_path, exception=error)
            raise ProductError('ALIGNMENT_RUNTIME_UNAVAILABLE', 'ALIGNED', 'MFA_LAUNCH_FAILED') from error
        grid = folder / 'aligned/item000.TextGrid'
        if completed.returncode != 0:
            retain_alignment_failure(settings, folder, audio_path, returncode=completed.returncode)
            if no_alignments_reported(folder / 'alignment.log'):
                # Successful runtime setup can still yield no usable evidence. The
                # pipeline already handles None as ABSTAINED, without guessed spans.
                return None
            raise ProductError('ALIGNMENT_RUNTIME_UNAVAILABLE', 'ALIGNED', 'MFA_EXECUTION_FAILED')
        if not grid.is_file():
            return None
        from speech_xray.alignment.textgrid_parser import parse_textgrid
        try:
            return parse_textgrid(grid)
        except ValueError:
            return None
