import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function MarkdownMessage({text}: {text: string}) {
  return <div className="markdown-message">
    <Markdown remarkPlugins={[remarkGfm]} skipHtml components={{
      a: ({children, href}) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
      img: ({alt}) => <span>{alt || 'Изображение'}</span>,
      table: ({children}) => <div className="markdown-table"><table>{children}</table></div>,
    }}>{text}</Markdown>
  </div>;
}
