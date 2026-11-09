import { ImageResponse } from "next/og";
import { corporate } from "@suseelkrishna/fieryfusion-tokens/tokens";

/** The browser tab icon: the same "RA" monogram as the Logo component, in the kit's accent colors. */

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 8,
          background: corporate.accent,
          color: corporate["on-accent"],
          fontSize: 15,
          fontWeight: 700,
          letterSpacing: -0.3,
        }}
      >
        RA
      </div>
    ),
    size,
  );
}
