import { Fragment } from "react";

const URL_RE = /(https?:\/\/[^\s<>"']+[^\s<>"'.,;:!?)\]])/g;

/** Free text for notes: line breaks are kept and http(s) addresses become links (nothing else is interpreted). */
export function NoteText({ text }: { text: string }) {
  return (
    <div className="note-text">
      {text.split(URL_RE).map((part, i) =>
        i % 2 === 1 ? <a key={i} href={part} target="_blank" rel="noreferrer noopener">{part}</a> : <Fragment key={i}>{part}</Fragment>)}
    </div>
  );
}
