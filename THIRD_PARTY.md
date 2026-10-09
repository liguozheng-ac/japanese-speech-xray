# 第三方来源与许可

核查日期：2026-10-09。本文件记录源码／软件与模型／语料的不同权利边界。候选仅包括作者代码与说明，没有 vendored 第三方源码、环境二进制、模型权重、语料或参考 WAV。正式自有源码许可证为 SOURCE_LICENSE_DECISION_PENDING。

## 运行依赖

| 软件 | 实际版本 | 许可证据 | 使用与分发边界 |
| --- | --- | --- | --- |
| librosa | 1.0.0 | [官方 ISC](https://github.com/librosa/librosa/blob/3e4ff7bf5898ac5b326e7dee56463b4b325b91cb/LICENSE.md)；安装包许可证已读取 | pYIN／RMS 依赖，仅安装不 vendoring |
| NumPy | 2.5.3 | 安装包 BSD-3-Clause 及 bundled 0BSD / MIT / Zlib / CC0 notices | 数值依赖，保留包内全部 notices |
| SciPy | 1.18.1 | 安装包 BSD-3-Clause 及内置组件 notices | 数值依赖 |
| Numba | 0.68.0 | 安装包 BSD-2-Clause 与 third-party notices | CPU 数值执行 |
| llvmlite | 0.50.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception（安装包） | 不能仅按一张 BSD 许可处理全部组件 |
| SoundFile | 0.14.0 | BSD-3-Clause（安装包） | 音频解码 |
| libsndfile | 1.2.2 | LGPL-2.1-or-later（conda-forge 包记录） | 独立安装，不随候选发布 DLL |
| SudachiPy | 0.6.11 | [官方 Apache-2.0](https://github.com/WorksApplications/SudachiPy/blob/develop/LICENSE)；安装元数据 | 日语词语读音；官方分支页面不能代替安装包版本身份 |
| SudachiDict-core | 20260116 | [官方许可](https://github.com/WorksApplications/SudachiDict/blob/develop/LICENSE-2.0.txt) 与安装包 Apache-2.0 / notices | 包管理器取得字典，候选不附字典二进制 |
| FastAPI / Pydantic | 0.142.2 / 2.13.5 | 安装包 MIT | HTTP／数据契约 |
| Starlette / Uvicorn / HTTPX | 1.7.0 / 0.54.0 / 0.28.1 | 安装包 BSD-3-Clause | HTTP 工程 |
| python-multipart | 0.0.32 | 安装包 Apache-2.0 | 表单上传 |

直接及环境传递依赖的实际版本、许可元数据、官方 URL 见 [依赖清单](docs/DEPENDENCY-LICENSES.md)。第三方包内 copyright／NOTICE 不能被项目许可证替换。仓库没有再分发整个环境；若将来打包应用／容器，需重新审核环境二进制及各 bundled 组件的分发义务。历史 MFA 环境含 GPL FFmpeg 等工具，不能整体标 MIT。

librosa 来源身份为官方 librosa/librosa，核查 Commit 3e4ff7bf5898ac5b326e7dee56463b4b325b91cb；本地使用包管理器安装版，不是本地 Git clone。其他 pip／Conda 包同样按实际包版本与哈希锁记录，不捏造 Git HEAD。

## 可选对齐与研究来源

| 来源 | 版本／身份 | 许可 | 本候选 |
| --- | --- | --- | --- |
| [MFA 官方](https://github.com/MontrealCorpusTools/Montreal-Forced-Aligner) | 3.4.2（原项目实际包版本） | [MIT](https://github.com/MontrealCorpusTools/Montreal-Forced-Aligner/blob/v3.4.2/LICENSE) | 自有 CLI 适配源码；不附 MFA 源码／运行环境 |
| [Narabas 官方 darashi/narabas](https://github.com/darashi/narabas) | b5e6511ce24dd2f14fc633ed5a23214225ca3eb7 | [源码 MIT](https://github.com/darashi/narabas/blob/b5e6511ce24dd2f14fc633ed5a23214225ca3eb7/LICENSE) | 自有历史适配器未默认启用；ONNX 权重许可未确认，排除 |
| [WhisperX 官方 m-bain/whisperX](https://github.com/m-bain/whisperX) | 771b4a14a9486f8fd5aef18ef49e35d639523dd3 | [BSD-2-Clause](https://github.com/m-bain/whisperX/blob/771b4a14a9486f8fd5aef18ef49e35d639523dd3/LICENSE) | 离线研究来源；源码、依赖与模型不进入候选 |
| [Silero 官方 snakers4/silero-vad](https://github.com/snakers4/silero-vad) | 1e261b036686cd0017d500ee96acd1c4ba572a9d | [MIT](https://github.com/snakers4/silero-vad/blob/1e261b036686cd0017d500ee96acd1c4ba572a9d/LICENSE) | 离线研究来源；不进入候选 |

上述身份来自原有冻结记录并对官方许可核查；本轮没有换 fork、下载模型或激活新链路。

## MFA 资源

Michael McAuliffe / Morgan Sonderegger：Japanese MFA [声学模型 v3.0.0](https://mfa-models.readthedocs.io/en/latest/acoustic/Japanese/Japanese%20MFA%20acoustic%20model%20v3_0_0.html)、[词典 v3.0.0](https://mfa-models.readthedocs.io/en/latest/dictionary/Japanese/Japanese%20MFA%20dictionary%20v3_0_0.html)、[G2P v2.0.1a](https://mfa-models.readthedocs.io/en/latest/g2p/Japanese/Japanese%20MFA%20G2P%20model%20v2_0_1a.html)，官方资源页标注 CC BY 4.0。候选只保留 release URL 与 SHA-256 身份说明，没有资源本体。自行取得与再分发需要遵循资源许可、归属与修改说明，不能套用 MFA 软件 MIT。

## JVS 与 Haruka

[JVS 官方语料说明](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_corpus) 对音频研究／个人使用、商业使用与再分发区分处理；tag／仓库的 CC BY-SA 声明不能推广覆盖全部音频。JVS 原始 WAV、真实转写、参考统计与研究派生结果均排除；只保留自有处理方法和独立编写的结构夹具。

Haruka 来自 Windows Desktop 的合成声音。[Microsoft SpeechSynthesizer 文档](https://learn.microsoft.com/en-us/uwp/api/windows.media.speechsynthesis.speechsynthesizer) 与 [系统声音说明](https://support.microsoft.com/en-us/accessibility/windows/narrator/appendix-a-supported-languages-and-voices) 能说明来源，不能据此确认这些 WAV 的 GitHub 再分发许可；Azure 神经 TTS 条款不作为 Desktop 声音的替代依据。标记 LICENSE_REVIEW_REQUIRED，三份 WAV、相关私人结果和派生音高截图全部排除。

用户原创前端和背景视频是主动保留私有，不是发现第三方权利冲突。仅采用本任务许可范围内的真实空态截图，见截图审核；截图与前端源码许可不混同。
