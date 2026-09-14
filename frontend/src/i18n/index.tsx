import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from 'react';
import { es, type Dictionary, type TranslationKey } from './es';

export type Locale = 'es';
export type TranslationVars = Record<string, string | number>;

interface I18nContextValue {
  locale: Locale;
  t: (key: TranslationKey, vars?: TranslationVars) => string;
  formatDate: (value: Date | string | number, options?: Intl.DateTimeFormatOptions) => string;
  formatDateTime: (
    value: Date | string | number,
    options?: Intl.DateTimeFormatOptions,
  ) => string;
  formatNumber: (value: number, options?: Intl.NumberFormatOptions) => string;
}

const DICTIONARIES: Record<Locale, Dictionary> = { es };

const DEFAULT_LOCALE: Locale = 'es';

const INTL_LOCALES: Record<Locale, string> = {
  es: 'es-ES',
};

function interpolate(template: string, vars?: TranslationVars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, token: string) => {
    const value = vars[token];
    return value === undefined ? match : String(value);
  });
}

function resolve(dictionary: Dictionary, key: TranslationKey, vars?: TranslationVars): string {
  // `key` está tipada contra el diccionario de `es`, por lo que siempre existe.
  const template = dictionary[key] ?? es[key] ?? key;
  return interpolate(template, vars);
}

const fallbackContext: I18nContextValue = {
  locale: DEFAULT_LOCALE,
  t: (key, vars) => resolve(DICTIONARIES[DEFAULT_LOCALE], key, vars),
  formatDate: (value, options) =>
    new Intl.DateTimeFormat(INTL_LOCALES[DEFAULT_LOCALE], {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      ...options,
    }).format(new Date(value)),
  formatDateTime: (value, options) =>
    new Intl.DateTimeFormat(INTL_LOCALES[DEFAULT_LOCALE], {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      ...options,
    }).format(new Date(value)),
  formatNumber: (value, options) =>
    new Intl.NumberFormat(INTL_LOCALES[DEFAULT_LOCALE], options).format(value),
};

const I18nContext = createContext<I18nContextValue>(fallbackContext);

export function I18nProvider({
  locale = DEFAULT_LOCALE,
  children,
}: {
  locale?: Locale;
  children: ReactNode;
}) {
  const value = useMemo<I18nContextValue>(() => {
    const dictionary = DICTIONARIES[locale] ?? es;
    const intlLocale = INTL_LOCALES[locale] ?? INTL_LOCALES[DEFAULT_LOCALE];

    return {
      locale,
      t: (key, vars) => resolve(dictionary, key, vars),
      formatDate: (input, options) =>
        new Intl.DateTimeFormat(intlLocale, {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
          ...options,
        }).format(new Date(input)),
      formatDateTime: (input, options) =>
        new Intl.DateTimeFormat(intlLocale, {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          ...options,
        }).format(new Date(input)),
      formatNumber: (input, options) =>
        new Intl.NumberFormat(intlLocale, options).format(input),
    };
  }, [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useTranslation() {
  const { t: translate, formatDate, formatDateTime, formatNumber, locale } =
    useContext(I18nContext);

  const t = useCallback(
    (key: TranslationKey, vars?: TranslationVars) => translate(key, vars),
    [translate],
  );

  return { t, locale, formatDate, formatDateTime, formatNumber };
}

export { es };
export type { TranslationKey, Dictionary };
