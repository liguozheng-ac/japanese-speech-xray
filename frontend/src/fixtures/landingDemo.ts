/** Eight authored multi-peak micro-waveform profiles, reused deterministically. */
export const microWaveformProfiles = [
  [
    0.08, 0.16, 0.35, 0.68, 0.42, 0.91, 0.24, 0.5, 0.28, 0.74, 0.39, 0.16, 0.48,
    0.62, 0.22, 0.37, 0.14, 0.08,
  ],
  [
    0.06, 0.25, 0.51, 0.29, 0.7, 0.36, 0.18, 0.6, 0.89, 0.4, 0.63, 0.21, 0.45,
    0.28, 0.53, 0.14, 0.19, 0.05,
  ],
  [
    0.11, 0.37, 0.62, 0.21, 0.48, 0.84, 0.33, 0.57, 0.2, 0.41, 0.72, 0.26, 0.52,
    0.18, 0.35, 0.61, 0.24, 0.09,
  ],
  [
    0.07, 0.18, 0.43, 0.78, 0.3, 0.56, 0.21, 0.66, 0.39, 0.14, 0.48, 0.9, 0.32,
    0.62, 0.24, 0.4, 0.15, 0.06,
  ],
  [
    0.09, 0.31, 0.64, 0.35, 0.18, 0.54, 0.88, 0.4, 0.7, 0.2, 0.36, 0.61, 0.28,
    0.46, 0.17, 0.55, 0.25, 0.1,
  ],
  [
    0.05, 0.2, 0.48, 0.22, 0.75, 0.32, 0.6, 0.19, 0.44, 0.85, 0.36, 0.53, 0.24,
    0.67, 0.29, 0.14, 0.3, 0.08,
  ],
  [
    0.1, 0.26, 0.56, 0.38, 0.81, 0.24, 0.47, 0.66, 0.29, 0.51, 0.2, 0.73, 0.42,
    0.15, 0.58, 0.33, 0.18, 0.07,
  ],
  [
    0.06, 0.34, 0.72, 0.28, 0.49, 0.17, 0.61, 0.39, 0.92, 0.25, 0.55, 0.33,
    0.76, 0.2, 0.45, 0.15, 0.24, 0.09,
  ],
];

/** Independent, synthetic Landing Page demonstration, not an API response.
 * Durations here are authored seconds, NOT the normalized demoAnalysis values.
 * The distribution and waveforms are illustrative, not JVS measurements.
 * Phone labels are a simplified focus illustration, not a full transcription.
 */
export const landingDemo = {
  sentence: "新しいスマートフォンを机に置きました。",
  words: ["新しい", "スマートフォン", "を", "机に", "置きました"],
  mora: ["ス", "マー", "ト", "フォ", "ン"],
  phones: ["/s/", "/aː/", "/t/", "/o/", "/n/"],
  durationSeconds: 1.68,
  referenceMedianSeconds: 2.04,
  speakerCount: 100,
  sentenceContextEquivalent: false,
  // One contiguous target interval in an authored illustrative timeline.
  targetInterval: { startSeconds: 2.98, endSeconds: 4.66 },
  detailWindow: { startSeconds: 0, endSeconds: 8.4 },
  timelineTicks: [0.5, 2, 3.5, 5, 6.5],
  waveform: Array.from({ length: 280 }, (_, i) => {
    const x = i / 279;
    const envelope = Math.sin(Math.PI * x) ** 0.75;
    const phrase = 0.18 + 0.82 * Math.abs(Math.sin(x * 15.2 - 0.6));
    return (
      0.025 + envelope * phrase * (0.2 + 0.8 * Math.abs(Math.sin(i * 1.79)))
    );
  }),
  distribution: Array.from({ length: 42 }, (_, i) => {
    const x = 0.5 + (i / 41) * 2.75;
    return (
      Math.exp(-0.5 * ((x - 2.04) / 0.47) ** 2) *
      (0.86 + 0.14 * Math.sin(i * 1.9) ** 2)
    );
  }),
};
