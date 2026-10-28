export class ObjectUrls {
  private urls = new Set<string>();
  create(blob: Blob) {
    const url = URL.createObjectURL(blob);
    this.urls.add(url);
    return url;
  }
  release(url: string) {
    if (this.urls.delete(url)) URL.revokeObjectURL(url);
  }
  clear() {
    this.urls.forEach((url) => URL.revokeObjectURL(url));
    this.urls.clear();
  }
}
