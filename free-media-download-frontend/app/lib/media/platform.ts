export function detectPlatform(value: string) {
  try {
    const first = value.split(/[\n\s]+/).find(Boolean);
    if (!first) return null;
    const host = new URL(first).hostname.toLowerCase();
    if (host.includes("youtube.com") || host === "youtu.be") return "YouTube";
    if (host.includes("bilibili.com") || host === "b23.tv") return "Bilibili";
    if (host.includes("douyin.com")) return "Douyin";
    if (host.includes("xiaohongshu.com") || host === "xhslink.com") return "Xiaohongshu";
    if (host.includes("weibo.com")) return "Weibo";
    if (host.includes("tiktok.com")) return "TikTok";
    if (host.includes("instagram.com")) return "Instagram";
    if (host.includes("facebook.com") || host === "fb.watch") return "Facebook";
    if (host === "x.com" || host.includes("twitter.com")) return "X";
    if (host.includes("vimeo.com")) return "Vimeo";
    return host;
  } catch {
    return null;
  }
}
