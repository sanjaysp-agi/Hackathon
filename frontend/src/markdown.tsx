import { Fragment } from "react";

/** Inline formatting: **bold**, `code`. Returns an array of React nodes. */
function inline(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  // Split on **bold** and `code`, keeping the delimiters' content.
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[2] != null) {
      nodes.push(<strong key={`${keyPrefix}-b${i}`}>{m[2]}</strong>);
    } else if (m[3] != null) {
      nodes.push(
        <code key={`${keyPrefix}-c${i}`} style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.92em" }}>
          {m[3]}
        </code>
      );
    }
    last = m.index + m[0].length;
    i++;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/**
 * Minimal, dependency-free Markdown renderer for the subset the agent emits:
 * headings (#, ##), bullet lists (-, *), **bold**, `code`, and paragraphs with
 * line breaks. Good enough for grounded chat answers; no external library.
 */
export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  let para: string[] = [];
  let key = 0;

  const flushList = () => {
    if (!list.length) return;
    const items = [...list];
    blocks.push(
      <ul key={`ul${key++}`} style={{ margin: "6px 0", paddingLeft: 18 }}>
        {items.map((it, j) => (
          <li key={j} style={{ margin: "2px 0" }}>{inline(it, `li${key}-${j}`)}</li>
        ))}
      </ul>
    );
    list = [];
  };
  const flushPara = () => {
    if (!para.length) return;
    const joined = para.join(" ");
    blocks.push(
      <p key={`p${key++}`} style={{ margin: "6px 0" }}>{inline(joined, `p${key}`)}</p>
    );
    para = [];
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const trimmed = line.trim();

    if (trimmed === "") {
      flushList();
      flushPara();
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(trimmed);
    if (heading) {
      flushList();
      flushPara();
      const level = heading[1].length;
      blocks.push(
        <div
          key={`h${key++}`}
          style={{ fontWeight: 650, fontSize: level <= 2 ? 14 : 13, margin: "8px 0 4px" }}
        >
          {inline(heading[2], `h${key}`)}
        </div>
      );
      continue;
    }
    const bullet = /^[-*]\s+(.*)$/.exec(trimmed);
    if (bullet) {
      flushPara();
      list.push(bullet[1]);
      continue;
    }
    // ordinary text line → paragraph
    flushList();
    para.push(trimmed);
  }
  flushList();
  flushPara();

  return <Fragment>{blocks}</Fragment>;
}
