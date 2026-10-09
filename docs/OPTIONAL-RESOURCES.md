# 可选实验与参考资源

基础 WAV 准入、句子目录和 pYIN 不要求任何大型语音模型。这里保留原适配器的资源边界，不承诺只下载模型即可复现私有参考结果。

## MFA

MFA 软件 3.4.2 使用 MIT。历史精确 Windows 环境包 URL 锁见 task002-conda-win-64.explicit.txt；不会自动安装该大环境。音高环境不能替代 MFA/Kaldi 工具环境。

官方声学模型 japanese_mfa v3.0.0、字典 v3.0.0、G2P v2.0.1a 的来源、哈希在 task002-resources.json，资源本体未提供。官方页面说明 CC BY 4.0；如自行获取或再分发，保留 McAuliffe / Sonderegger 归属、链接、许可与修改说明，勿以 MIT 代替模型许可。来源详见 [THIRD_PARTY](../THIRD_PARTY.md)。

完整实验 API 还需配置合法、验证的参考 profiles、manifest、descriptor 和 measurement identity；这些研究材料不公开。缺少资源保持 503，不将 MFA 自动边界视为真值。显式配置通过 SPEECH_XRAY_CONFIG 读取；Settings、Resource、ReferenceResource 在源码中定义。path／sha256 必须对应实际文件，不能使用假的哈希使 readiness 通过。SPEECH_XRAY_ALIGNER=mfa 必须与显式配置一致。

## 合成参考

Haruka Desktop 的 WAV 再分发依据尚未确认，所以本仓库无参考 WAV。默认返回 SYNTHETIC_REFERENCE_UNAVAILABLE，用户 F0 独立保留。可选目录为 data/optional-reference-audio 或 SPEECH_XRAY_REFERENCE_AUDIO_DIR；既有参考读取器仍检查 manifest 的 voice、type、同句文本和冻结 SHA-256。任意同名 WAV 不会被误当成已接受参考。

未提供生成 Haruka WAV 的前端／本机脚本，也未借用 Azure 神经 TTS 的条款证明 Windows Desktop 语音权利。合成参考始终不是母语者准确性标准。

## JVS、Narabas 与离线研究

JVS 实际音频、标注、参考 profiles 与分布不提供；适配器只是自有处理方法。原语料的本地研究许可不能自动推广为 GitHub 再分发许可。

Narabas 官方源码身份、版本和 MIT 已记录，但 ONNX 权重、冻结序列、接受配置和 300 条研究结果均未进入候选。默认 MFA，Narabas 不生产激活。WhisperX、Silero 仅列作既有离线研究来源，未作为此候选运行时依赖安装。
