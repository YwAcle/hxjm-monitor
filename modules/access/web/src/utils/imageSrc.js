const DATA_IMAGE_BASE64_PATTERN = /^data:image\/([a-zA-Z0-9.+-]+);base64[:,]/;

const BASE64_IMAGE_PREFIXES = [
  { prefix: '/9j', mime: 'image/jpeg' },
  { prefix: 'iVBOR', mime: 'image/png' },
  { prefix: 'R0lGOD', mime: 'image/gif' },
  { prefix: 'UklGR', mime: 'image/webp' }
];

export function normalizeImageSrc(image) {
  if (!image || typeof image !== 'string') {
    return '';
  }

  const trimmed = image.trim();
  if (!trimmed) {
    return '';
  }

  if (DATA_IMAGE_BASE64_PATTERN.test(trimmed)) {
    return trimmed.replace(';base64:', ';base64,');
  }

  if (/^https?:\/\//i.test(trimmed) || trimmed.startsWith('/')) {
    const base64Image = BASE64_IMAGE_PREFIXES.find(({ prefix }) => trimmed.startsWith(prefix));
    if (base64Image) {
      return `data:${base64Image.mime};base64,${trimmed}`;
    }

    return trimmed;
  }

  const base64Image = BASE64_IMAGE_PREFIXES.find(({ prefix }) => trimmed.startsWith(prefix));
  const mime = base64Image ? base64Image.mime : 'image/jpeg';
  return `data:${mime};base64,${trimmed}`;
}
