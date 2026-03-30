import type { DocumentSection } from "../types";

export function parseSections(doc: string): DocumentSection[] {
  const chunks = doc.split(/^## /m).slice(1);
  return chunks.map((chunk) => {
    const newlineIdx = chunk.indexOf("\n");
    if (newlineIdx === -1) return { title: chunk.trim(), content: "" };
    return {
      title: chunk.slice(0, newlineIdx).trim(),
      content: chunk.slice(newlineIdx + 1),
    };
  });
}
