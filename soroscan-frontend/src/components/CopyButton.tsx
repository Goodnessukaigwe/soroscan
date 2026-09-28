import React, { useState, useCallback, useEffect } from 'react';

interface CopyButtonProps {
  text: string;
  className?: string;
}

export const CopyButton: React.FC<CopyButtonProps> = ({ text, className = '' }) => {
  const [isCopied, setIsCopied] = useState(false);

  useEffect(() => {
    let timeout: NodeJS.Timeout;
    if (isCopied) {
      timeout = setTimeout(() => {
        setIsCopied(false);
      }, 2000);
    }
    return () => {
      if (timeout) clearTimeout(timeout);
    };
  }, [isCopied]);

  const fallbackCopyTextToClipboard = (textToCopy: string) => {
    const textArea = document.createElement("textarea");
    textArea.value = textToCopy;
    
    // Avoid scrolling to bottom
    textArea.style.top = "0";
    textArea.style.left = "0";
    textArea.style.position = "fixed";

    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
      document.execCommand('copy');
    } catch (err) {
      console.error('Fallback: Oops, unable to copy', err);
    }

    document.body.removeChild(textArea);
  };

  const handleCopy = useCallback(() => {
    if (!navigator.clipboard) {
      fallbackCopyTextToClipboard(text);
      setIsCopied(true);
      return;
    }
    navigator.clipboard.writeText(text).then(() => {
      setIsCopied(true);
    }).catch(err => {
      console.error('Async: Could not copy text: ', err);
      // Try fallback if async fails
      fallbackCopyTextToClipboard(text);
      setIsCopied(true);
    });
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={`inline-flex items-center justify-center p-1 text-gray-500 transition-colors rounded-md hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500 ${className}`}
      title="Copy to clipboard"
      aria-label="Copy to clipboard"
    >
      {isCopied ? (
        <svg
          className="w-4 h-4 text-green-500 transition-transform duration-300 scale-110"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg
          className="w-4 h-4 transition-transform duration-300 hover:scale-110"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      )}
    </button>
  );
};

export default CopyButton;
