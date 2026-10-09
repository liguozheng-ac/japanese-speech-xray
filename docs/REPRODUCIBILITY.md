# 后端复现

验证日期：2026-10-09。Windows x64、Python 3.13.15；外部包从官方 conda-forge 与 PyPI 安装。不要把原产品目录或私人音频作为依赖复制。

## 1. 精确环境与源码安装

已实际创建独立 prefix 并安装冻结 HTTP 层依赖；第一次未激活环境时 SoundFile 无法加载 libsndfile.dll。必须激活环境或按下方方式显式设置本进程 PATH。

```powershell
conda create --prefix ./.venv --file environment-public-win-64.explicit.txt
conda activate "$PWD/.venv"
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
python -m pip check
```

本次环境创建使用既有官方包缓存，pip 安装通过官方注册表获取 HTTP 依赖；没有复用原项目 Python prefix，也没有复制其私人配置。包 URL/MD5 锁不能保证上游永久可下载。

如已经创建 prefix，但当前 PowerShell 尚未激活，可用同样经过验证的局部方式：

```powershell
$prefix = Join-Path $PWD '.venv'
$env:PATH = "$prefix;$prefix/Library/bin;$prefix/Scripts;$env:PATH"
& "$prefix/python.exe" -m pip check
& "$prefix/python.exe" scripts/run_tests.py
```

测试／示例脚本从 checkout 定位源代码。editable 安装让 uvicorn 导入包；wheel 只打包 Python 模块，不附句子表、配置、模型或网页，因此常规运行使用源码 checkout。

## 2. 工程测试与真实 F0

```powershell
python scripts/run_tests.py
python -m compileall -q services scripts tests examples
python examples/prosody_smoke.py
```

默认示例现场生成 2 秒、16 kHz Mono PCM16 的 220 Hz 正弦输入，前后各约 0.3 秒静音。明确标为 ENGINEERING_TONE_NOT_HUMAN_SPEECH。实际获得 100 帧，其中 75 帧准入；中位数约 220.64 Hz。没有从私人 Haruka／JVS 文件读取音频。

用户自行提供合法 WAV：

```powershell
python examples/prosody_smoke.py --audio ./my-input.wav --save-json ./my-curve.json
```

输出 frame 含 time_ms、f0_hz（可能为 null）、voiced、pyin_voiced、voiced_probability、rms_dbfs。提供音频属于本地用户操作；不要提交 WAV 或个人曲线。

## 3. 启动本地 API

清除当前 shell 的旧产品配置变量，或从没有旧变量的干净 shell 执行。默认配置只引用当前 checkout。

```powershell
python -m uvicorn speech_xray.api.app:app --host 127.0.0.1 --port 8000
```

新 shell 激活同一环境，生成忽略目录中的工程 WAV，再调用 API：

```powershell
New-Item -ItemType Directory -Force data/private/smoke | Out-Null
python examples/prosody_smoke.py --generate-wav data/private/smoke/engineering.wav
curl.exe http://127.0.0.1:8000/api/v1/health/live
curl.exe http://127.0.0.1:8000/api/v1/health/ready
curl.exe http://127.0.0.1:8000/api/v1/prompts
curl.exe -X POST http://127.0.0.1:8000/api/prosody/v1/curves -F "prompt_id=learner-v1-001" -F "audio=@data/private/smoke/engineering.wav;type=audio/wav"
```

以上 localhost 地址仅是 API 运行示例，不是已上线 Demo。

| 检查 | 无外部资源时预期 |
| --- | --- |
| /api/v1/health/live | 200 / LIVE |
| /api/v1/prompts | 200 / 三条受控句子 |
| /openapi.json | 200，含独立 prosody 接口 |
| /api/v1/health/ready | 503 / NOT_READY，实验对齐与参考未提供 |
| 工程音高 POST | 200，learner AVAILABLE；reference 为 null，SYNTHETIC_REFERENCE_UNAVAILABLE |
| 全静音 POST | 200，learner ABSTAINED / LOW_ENERGY_NO_F0 |
| 立体声、MP3 POST | 422，明确拒绝 |
| /api/v1/analyses | 503 / REFERENCE_ARTIFACT_MISSING；不伪造实验结果 |

用户音高 WAV 只在此接口内存中解码处理，不进入参考缓存；multipart 解析器可能使用操作系统临时 spool，不能把此表述扩大为所有 HTTP 上传绝对不会触盘。实验对齐需要临时工作目录，已有 orchestrator 负责清理，debug_retention 默认 false。

## 4. 提取参数

原 PCM 采样率，不重采样；fmin=50 Hz、fmax=600 Hz；帧长为大于等于 80 ms 的二次幂，hop 约 20 ms；center=true、constant padding；n_thresholds=100、beta=(2,18)、resolution=0.1。显示门禁 RMS > -60 dBFS、voiced probability >= 0.1；少于 5 个准入帧弃权。精确其余参数以 prosody/extract.py 返回 parameters 为准；与冻结原算法一致。

## 5. 外部实验边界

MFA、参考 profiles、Haruka、Narabas 和真实语料不包含；参阅 [资源说明](OPTIONAL-RESOURCES.md)。离线脚本可以合法处理用户自己准备的数据，但本轮没有重建语料或更换资源。私人集成测试的原始文件不被删除；公开测试中的 skip 是缺失资源，不是 PASS。
