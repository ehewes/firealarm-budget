type Search = Record<string, string | string[] | undefined>;

/**
 * The store URL from whatever followed our domain:
 *   go.edenmatrix.xyz/https://www.joinfleek.com/collections/nike?page=2
 *   go.edenmatrix.xyz/www.joinfleek.com/collections/nike
 *
 * Browsers and Next collapse the `//` in a path, so `https://` arrives as `https:/`.
 * The API normalises and validates again (allowlist included); this only rebuilds it.
 */
export function targetFromPath(segments: string[], search: Search): string {
  const path = segments
    .map((segment) => {
      try {
        return decodeURIComponent(segment);
      } catch {
        return segment;
      }
    })
    .join("/");
  let url = path.replace(/^(https?):\/+/i, "$1://");
  if (!/^https?:\/\//i.test(url)) url = `https://${url}`;

  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(search)) {
    for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) {
      query.append(key, item);
    }
  }
  const qs = query.toString();
  return qs ? `${url}${url.includes("?") ? "&" : "?"}${qs}` : url;
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
