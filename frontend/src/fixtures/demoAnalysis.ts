/** Authored UI fixture, NOT a backend response or a measured recording.
 * Timings and distribution values are synthetic. N=100 represents the product's
 * independent JVS-speaker reference design, not 100 copies of this sentence.
 * マ and ー share the original long-phone interval; no invented midpoint.
 */
export const demoAnalysis = {
  id: "visual-demo-001",
  origin: "AUTHORED_UI_FIXTURE",
  promptId: "learner-v1-001",
  prompt: "新しいスマートフォンを机に置きました。",
  target: { word: "スマートフォン", mora: "マー", phone: "aː", moraSpan: 2 },
  audio: { durationMs: 4280, label: "DEMO / 001", isPlaceholder: true },
  waveform: Array.from({ length: 168 }, (_, i) => {
    const envelope = Math.sin((i / 167) * Math.PI) ** 0.6;
    const syllables = 0.22 + 0.78 * Math.abs(Math.sin(i * 0.17 + 0.4));
    return Math.max(
      0.025,
      envelope * syllables * (0.28 + Math.abs(Math.sin(i * 1.73)) * 0.72),
    );
  }),
  wordSegments: [
    { label: "新しい", startMs: 260, endMs: 1160 },
    { label: "スマートフォン", startMs: 1160, endMs: 2440 },
    { label: "を", startMs: 2440, endMs: 2620 },
    { label: "机", startMs: 2620, endMs: 3010 },
    { label: "に", startMs: 3010, endMs: 3160 },
    { label: "置きました", startMs: 3160, endMs: 4050 },
  ],
  detailWindow: { startMs: 1160, endMs: 2440 },
  moraGroups: [
    { label: "ス", startMs: 1160, endMs: 1380, target: false },
    { label: "マー", startMs: 1380, endMs: 1720, target: true },
    { label: "ト", startMs: 1720, endMs: 1950, target: false },
    { label: "フォ", startMs: 1950, endMs: 2250, target: false },
    { label: "ン", startMs: 2250, endMs: 2440, target: false },
  ],
  phones: [
    { label: "s", startMs: 1160, endMs: 1270 },
    { label: "ɨ", startMs: 1270, endMs: 1380 },
    { label: "m", startMs: 1380, endMs: 1480 },
    { label: "aː", startMs: 1480, endMs: 1720 },
    { label: "t", startMs: 1720, endMs: 1820 },
    { label: "o", startMs: 1820, endMs: 1950 },
    { label: "ɸ", startMs: 1950, endMs: 2050 },
    { label: "o", startMs: 2050, endMs: 2250 },
    { label: "ɴ", startMs: 2250, endMs: 2440 },
  ],
  sharedLongPhoneSpan: {
    startMs: 1480,
    endMs: 1720,
    representations: ["マ", "ー"],
  },
  duration: {
    rawMs: 240,
    normalized: 1.68,
    medianRatio: 1.68 / 2.04,
    interpretation: "低于母语者参考中位数",
  },
  reference: {
    median: 2.04,
    q25: 1.78,
    q75: 2.31,
    min: 1.12,
    max: 3.02,
    speakerCount: 100,
    feature: "rate_normalized_duration",
    sentenceContextEquivalent: false,
    description: "该词的独立 JVS 母语者参考 · 完整句子语境不同",
  },
  realization: {
    canonical: { label: "完整长音形式", kana: "マー", phone: "aː" },
    reduced: { label: "实验性缩短形式", kana: "マ", phone: "a" },
    selected: "canonical",
    experimental: true,
    description: "本次声音证据更支持完整长音形式。",
  },
  availability: [
    { label: "长音定位", available: true },
    { label: "时间轴", available: true },
    { label: "时长", available: true },
    { label: "母语者参考", available: true },
    { label: "长音实现", available: true },
    { label: "音高证据", available: false },
  ],
  summary:
    "语速调整后的长音时长位于母语者参考中位数以下；实验性实现比较更支持完整长音形式。这两类证据描述声音的不同侧面，不构成经校准的发音质量判定。",
  scanStages: [
    "读取语音",
    "声音与文字对齐",
    "音拍拆分",
    "声学证据",
    "母语者参考",
    "长音实现证据",
    "证据整合",
  ],
} as const;
