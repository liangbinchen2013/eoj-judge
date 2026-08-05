import { useEffect } from 'react';
import { t } from '../i18n';
import { getSiteConfig } from './useSiteConfig';

const BASE_TITLE = getSiteConfig().site.name;

export function useDocumentTitle(title?: string) {
  useEffect(() => {
    if (title) {
      document.title = `${title} - ${BASE_TITLE}`;
    } else {
      document.title = BASE_TITLE;
    }
    return () => {
      document.title = BASE_TITLE;
    };
  }, [title]);
}

export function useDocumentTitleKey(key?: string) {
  const title = key ? t(key) : undefined;
  useDocumentTitle(title);
}
