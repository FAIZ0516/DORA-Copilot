/**
 * Types for the shared Zara avatar, which is a .jsx component consumed from
 * the Zara workspace's TypeScript project.
 *
 * That project deliberately excludes JavaScript -- it type-checks only its own
 * .ts/.tsx sources, so turning on `allowJs` to satisfy one import would pull
 * the entire untyped frontend into it. Declaring the component's surface here
 * keeps the boundary intact and the import typed.
 */

export interface ZaraAvatarProps {
  className?: string;
  /** Hides the image from assistive technology, for decorative placements. */
  decorative?: boolean;
  /** Rendered width and height in pixels. */
  size?: number;
}

declare function ZaraAvatar(props: ZaraAvatarProps): JSX.Element;

export default ZaraAvatar;
