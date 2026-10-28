export function elapsedLabel(start: number | undefined, now: number) {
  const seconds = start == null ? 0 : Math.floor(Math.max(0, now - start) / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
