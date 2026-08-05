const VALID_SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const VALID_USERNAME = /^[a-zA-Z0-9_]{3,20}$/;
const VALID_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const ALLOWED_LANGUAGES = ['python', 'cpp', 'java', 'javascript', 'c', 'go', 'rust'];
const MAX_SOURCE_CODE_LENGTH = 65535;

export function validateSlug(slug: string): string | null {
  if (!slug || slug.trim().length === 0) return 'Slug is required';
  if (!VALID_SLUG.test(slug)) return 'Slug must only contain lowercase letters, numbers, and hyphens';
  if (slug.length > 100) return 'Slug must be at most 100 characters';
  return null;
}

export function validateUsername(username: string): string | null {
  if (!username || username.trim().length === 0) return 'Username is required';
  if (!VALID_USERNAME.test(username)) return 'Username must be 3-20 characters, only letters, numbers, and underscores';
  return null;
}

export function validateEmail(email: string): string | null {
  if (!email || email.trim().length === 0) return 'Email is required';
  if (!VALID_EMAIL.test(email)) return 'Invalid email format';
  return null;
}

export function validateSourceCode(sourceCode: string): string | null {
  if (!sourceCode || sourceCode.trim().length === 0) return 'Source code is required';
  if (sourceCode.length > MAX_SOURCE_CODE_LENGTH) return `Source code must be at most ${MAX_SOURCE_CODE_LENGTH} characters`;
  return null;
}

export function validateLanguage(language: string): string | null {
  if (!language) return 'Language is required';
  if (!ALLOWED_LANGUAGES.includes(language)) return `Language must be one of: ${ALLOWED_LANGUAGES.join(', ')}`;
  return null;
}
