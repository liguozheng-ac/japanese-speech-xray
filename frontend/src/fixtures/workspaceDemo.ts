// Approved controlled prompts. These are display fixtures, never user history.
export const demoHistory = [
  {
    id: "smartphone",
    sentence: "新しいスマートフォンを机に置きました。",
    target: "スマートフォン",
    focus: "マー",
    reference: "ref010",
    canonicalVowel: "A",
  },
  {
    id: "debut",
    sentence: "来月、舞台でデビューします。",
    target: "デビュー",
    reference: "ref051",
    canonicalVowel: "U",
  },
  {
    id: "series",
    sentence: "このシリーズを週末に見ます。",
    target: "シリーズ",
    reference: "ref074",
    canonicalVowel: "I",
  },
] as const;
