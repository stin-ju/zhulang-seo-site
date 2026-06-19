// ABOUTME: 在客户端动态设置 document.title 与 meta description，供各页面挂载时调用。
import { useEffect } from 'react';

interface DocumentMetaOptions {
  title: string;
  description?: string;
}

export function useDocumentMeta({ title, description }: DocumentMetaOptions): void {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = title;

    let restoreDescription: (() => void) | null = null;
    if (description) {
      let metaEl = document.querySelector<HTMLMetaElement>('meta[name="description"]');
      let createdHere = false;
      if (!metaEl) {
        metaEl = document.createElement('meta');
        metaEl.setAttribute('name', 'description');
        document.head.appendChild(metaEl);
        createdHere = true;
      }
      const previousDescription = metaEl.getAttribute('content') ?? '';
      metaEl.setAttribute('content', description);
      restoreDescription = () => {
        if (!metaEl) return;
        if (createdHere) {
          metaEl.parentNode?.removeChild(metaEl);
        } else {
          metaEl.setAttribute('content', previousDescription);
        }
      };
    }

    return () => {
      document.title = previousTitle;
      if (restoreDescription) restoreDescription();
    };
  }, [title, description]);
}
