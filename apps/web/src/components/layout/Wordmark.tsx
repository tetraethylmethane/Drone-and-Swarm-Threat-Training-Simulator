/**
 * Official Drikr Systems logo (assets/brand/source/drikr-logo.png, processed to a transparent
 * ink version in assets/brand). The image carries the accessible name; height sets the size.
 */
export function Wordmark({ className = "", height = 18 }: { className?: string; height?: number }) {
  return (
    <img
      src="/brand/drikr-logo.png"
      alt="Drikr Systems"
      height={height}
      style={{ height, width: "auto" }}
      className={`block select-none ${className}`}
      draggable={false}
    />
  );
}
