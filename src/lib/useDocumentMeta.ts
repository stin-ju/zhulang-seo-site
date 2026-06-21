// ABOUTME: 在客户端动态设置 document.title / meta description / keywords / canonical / OG /
// Twitter Card / JSON-LD 等 SEO 标签，供各页面挂载时调用，组件卸载时还原。
import { useEffect } from 'react';

export const SITE_ORIGIN = 'https://zhulang.coze.site';
export const SITE_NAME = '2026世界杯 AI 预测大竞赛';

export interface DocumentMetaOptions {
  title: string;
  description?: string;
  keywords?: string;
  /** 站内绝对路径（以 / 开头），用于拼接 canonical 与 og:url */
  canonicalPath?: string;
  /** 默认 website */
  ogType?: 'website' | 'article' | 'profile';
  ogImage?: string;
  /** JSON-LD 结构化数据（对象或对象数组） */
  jsonLd?: Record<string, unknown> | Array<Record<string, unknown>>;
}

function ensureMetaByName(name: string): { el: HTMLMetaElement; created: boolean } {
  let el = document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  if (el) return { el, created: false };
  el = document.createElement('meta');
  el.setAttribute('name', name);
  document.head.appendChild(el);
  return { el, created: true };
}

function ensureMetaByProperty(property: string): { el: HTMLMetaElement; created: boolean } {
  let el = document.querySelector<HTMLMetaElement>(`meta[property="${property}"]`);
  if (el) return { el, created: false };
  el = document.createElement('meta');
  el.setAttribute('property', property);
  document.head.appendChild(el);
  return { el, created: true };
}

function ensureLinkByRel(rel: string): { el: HTMLLinkElement; created: boolean } {
  let el = document.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (el) return { el, created: false };
  el = document.createElement('link');
  el.setAttribute('rel', rel);
  document.head.appendChild(el);
  return { el, created: true };
}

type Restorer = () => void;

function applyMetaContent(
  el: HTMLMetaElement,
  created: boolean,
  content: string,
  cleanups: Restorer[],
): void {
  const prev = el.getAttribute('content') ?? '';
  el.setAttribute('content', content);
  cleanups.push(() => {
    if (created) {
      el.parentNode?.removeChild(el);
    } else {
      el.setAttribute('content', prev);
    }
  });
}

function applyLinkHref(
  el: HTMLLinkElement,
  created: boolean,
  href: string,
  cleanups: Restorer[],
): void {
  const prev = el.getAttribute('href') ?? '';
  el.setAttribute('href', href);
  cleanups.push(() => {
    if (created) {
      el.parentNode?.removeChild(el);
    } else {
      el.setAttribute('href', prev);
    }
  });
}

export function useDocumentMeta(options: DocumentMetaOptions): void {
  const {
    title,
    description,
    keywords,
    canonicalPath,
    ogType = 'website',
    ogImage,
    jsonLd,
  } = options;

  const jsonLdKey = jsonLd ? JSON.stringify(jsonLd) : '';

  useEffect(() => {
    const cleanups: Restorer[] = [];
    const previousTitle = document.title;
    document.title = title;
    cleanups.push(() => {
      document.title = previousTitle;
    });

    if (description) {
      const { el, created } = ensureMetaByName('description');
      applyMetaContent(el, created, description, cleanups);
    }

    if (keywords) {
      const { el, created } = ensureMetaByName('keywords');
      applyMetaContent(el, created, keywords, cleanups);
    }

    const url = canonicalPath ? `${SITE_ORIGIN}${canonicalPath}` : null;
    if (url) {
      const { el, created } = ensureLinkByRel('canonical');
      applyLinkHref(el, created, url, cleanups);
    }

    // Open Graph
    {
      const { el, created } = ensureMetaByProperty('og:title');
      applyMetaContent(el, created, title, cleanups);
    }
    if (description) {
      const { el, created } = ensureMetaByProperty('og:description');
      applyMetaContent(el, created, description, cleanups);
    }
    {
      const { el, created } = ensureMetaByProperty('og:type');
      applyMetaContent(el, created, ogType, cleanups);
    }
    if (url) {
      const { el, created } = ensureMetaByProperty('og:url');
      applyMetaContent(el, created, url, cleanups);
    }
    {
      const { el, created } = ensureMetaByProperty('og:site_name');
      applyMetaContent(el, created, SITE_NAME, cleanups);
    }
    if (ogImage) {
      const { el, created } = ensureMetaByProperty('og:image');
      applyMetaContent(el, created, ogImage, cleanups);
    }

    // Twitter Card
    {
      const { el, created } = ensureMetaByName('twitter:card');
      applyMetaContent(el, created, 'summary_large_image', cleanups);
    }
    {
      const { el, created } = ensureMetaByName('twitter:title');
      applyMetaContent(el, created, title, cleanups);
    }
    if (description) {
      const { el, created } = ensureMetaByName('twitter:description');
      applyMetaContent(el, created, description, cleanups);
    }
    if (ogImage) {
      const { el, created } = ensureMetaByName('twitter:image');
      applyMetaContent(el, created, ogImage, cleanups);
    }

    // JSON-LD
    if (jsonLd) {
      const items = Array.isArray(jsonLd) ? jsonLd : [jsonLd];
      const scripts: HTMLScriptElement[] = items.map((data) => {
        const s = document.createElement('script');
        s.type = 'application/ld+json';
        s.setAttribute('data-managed-jsonld', 'true');
        s.text = JSON.stringify(data);
        document.head.appendChild(s);
        return s;
      });
      cleanups.push(() => {
        for (const s of scripts) s.parentNode?.removeChild(s);
      });
    }

    return () => {
      // 反向执行 cleanup，保证嵌套场景下后挂载的先还原
      for (let i = cleanups.length - 1; i >= 0; i--) {
        cleanups[i]();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, description, keywords, canonicalPath, ogType, ogImage, jsonLdKey]);
}
