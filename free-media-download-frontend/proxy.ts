import { NextResponse, type NextRequest } from "next/server";
import { locales } from "./app/lib/i18n/locales";

function preferredLocale(request: NextRequest) {
  const accepted = request.headers.get("accept-language") ?? "";
  const ranked = accepted
    .split(",")
    .map((part) => {
      const [tag, quality] = part.trim().split(";q=");
      return { tag: tag.toLowerCase(), quality: Number(quality ?? 1) || 0 };
    })
    .sort((left, right) => right.quality - left.quality);
  return ranked.some(({ tag }) => tag === "zh" || tag.startsWith("zh-"))
    ? "zh-CN"
    : "en-US";
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasLocale = locales.some(
    (locale) => pathname === `/${locale}` || pathname.startsWith(`/${locale}/`),
  );
  if (hasLocale) return NextResponse.next();

  const locale = preferredLocale(request);
  const target = request.nextUrl.clone();
  target.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(target);
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|.*\\..*).*)",
  ],
};
