import zaraAvatar from "../../assets/zara-avatar.png";
import "./ZaraAvatar.css";

export default function ZaraAvatar({ className = "", decorative = false, size = 34 }) {
  const classes = ["zara-avatar", className].filter(Boolean).join(" ");

  return (
    <img
      className={classes}
      src={zaraAvatar}
      alt={decorative ? "" : "Zara"}
      aria-hidden={decorative ? "true" : undefined}
      width={size}
      height={size}
      style={{ "--zara-avatar-size": `${size}px` }}
    />
  );
}
