interface Props {
  urls: Record<string, string>;
  alt: string;
  sizes?: string;
  className?: string;
  width?: number | null;
  height?: number | null;
  eager?: boolean;
}

const WIDTHS = [320, 640, 1080] as const;

export function Picture({ urls, alt, sizes = "(max-width: 640px) 100vw, 640px", className, width, height, eager }: Props) {
  const set = (ext: string) => WIDTHS.filter((w) => urls[`${w}.${ext}`]).map((w) => `${urls[`${w}.${ext}`]} ${w}w`).join(", ");
  const fallback = urls["640.webp"] ?? urls["320.webp"] ?? Object.values(urls)[0] ?? "";
  return (
    <picture>
      {set("avif") ? <source type="image/avif" srcSet={set("avif")} sizes={sizes} /> : null}
      {set("webp") ? <source type="image/webp" srcSet={set("webp")} sizes={sizes} /> : null}
      <img src={fallback} alt={alt} className={className} width={width ?? undefined} height={height ?? undefined}
        loading={eager ? "eager" : "lazy"} decoding="async" />
    </picture>
  );
}
