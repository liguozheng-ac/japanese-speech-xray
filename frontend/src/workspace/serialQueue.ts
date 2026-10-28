// A fulfilled/rejected fetch must settle before another job can start.
// Transport uncertainty is handled by getNext() returning no job until explicitly resumed.
export class SerialQueue<T> {
  running = false;
  async kick(getNext: () => T | undefined, run: (job: T) => Promise<void>) {
    if (this.running) return;
    this.running = true;
    try {
      let job: T | undefined;
      while ((job = getNext()) !== undefined) await run(job);
    } finally { this.running = false; }
  }
}
