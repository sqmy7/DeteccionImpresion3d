import { ImageOff } from "lucide-react";
import { useState } from "react";
import { classColor, classLabel } from "../../config/defectClasses";
import type { FrameBox } from "../../lib/boxes";

/** A still frame with its detection boxes drawn on top, in percentages so they follow the image
 * at any size. */
export function AnnotatedImage({ src, alt, boxes = [] }: { src: string | null; alt: string; boxes?: FrameBox[] }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div className="flex aspect-video w-full flex-col items-center justify-center gap-1.5 rounded-lg bg-surface-2 text-xs text-faint">
        <ImageOff size={20} />
        Sin imagen
      </div>
    );
  }

  return (
    <div className="relative w-full overflow-hidden rounded-lg bg-surface-2">
      <img src={src} alt={alt} className="block h-auto w-full" onError={() => setFailed(true)} />
      {boxes.map((box, index) => {
        const color = classColor(box.className);
        return (
          <div
            key={index}
            className="pointer-events-none absolute border-2"
            style={{
              left: `${box.x1 * 100}%`,
              top: `${box.y1 * 100}%`,
              width: `${(box.x2 - box.x1) * 100}%`,
              height: `${(box.y2 - box.y1) * 100}%`,
              borderColor: color,
            }}
          >
            <span
              className="absolute left-0 -translate-y-full whitespace-nowrap px-1 text-[10px] font-semibold leading-4 text-black"
              style={{ backgroundColor: color, top: 0 }}
            >
              {classLabel(box.className)} {Math.round(box.confidence * 100)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
