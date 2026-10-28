# Offline asset generation using an already installed Japanese Windows voice.
# No service, model download or runtime TTS dependency.
param([string]$Voice = 'Microsoft Haruka Desktop')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$taskAssetRoot = Join-Path $PSScriptRoot '..\public\audio\reference'
New-Item -ItemType Directory -Force -Path $taskAssetRoot | Out-Null
$taskReadings = @(
  @{ prompt_id='learner-v1-001'; text='新しいスマートフォンを机に置きました。' },
  @{ prompt_id='learner-v1-002'; text='来月、舞台でデビューします。' },
  @{ prompt_id='learner-v1-003'; text='このシリーズを週末に見ます。' }
)
$taskSynth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $taskSynth.SelectVoice($Voice)
  if ($taskSynth.Voice.Culture.Name -ne 'ja-JP') { throw 'Selected voice must be Japanese.' }
  $taskSynth.Rate = 0
  $taskSynth.Volume = 100
  $taskFormat = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
  $taskAssets = foreach ($taskReading in $taskReadings) {
    $taskFile = Join-Path $taskAssetRoot ($taskReading.prompt_id + '.wav')
    $taskSynth.SetOutputToWaveFile($taskFile, $taskFormat)
    $taskSynth.Speak($taskReading.text)
    $taskSynth.SetOutputToNull()
    @{
      prompt_id=$taskReading.prompt_id; text=$taskReading.text; status='READY'; type='synthetic';
      engine='Windows SAPI / System.Speech'; voice=$taskSynth.Voice.Name; locale='ja-JP';
      sample_rate=24000; channels=1; format='PCM16 WAV'; rate=0;
      path=('audio/reference/' + $taskReading.prompt_id + '.wav');
      sha256=(Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash.ToLowerInvariant()
    }
  }
  @{ version=1; purpose='UX playback only; excluded from analysis and JVS population'; assets=@($taskAssets) } |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskAssetRoot 'manifest.json') -Encoding utf8
} finally { $taskSynth.Dispose() }
