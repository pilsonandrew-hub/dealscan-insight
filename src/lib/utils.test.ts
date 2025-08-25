import { describe, it, expect } from 'vitest';
import { cn } from './utils';

describe('utils', () => {
  describe('cn', () => {
    it('should merge class names correctly', () => {
      expect(cn('px-4 py-2', 'bg-blue-500')).toBe('px-4 py-2 bg-blue-500');
    });

    it('should handle conditional classes', () => {
      expect(cn('base-class', true && 'conditional-class', false && 'hidden-class'))
        .toBe('base-class conditional-class');
    });

    it('should handle conflicting tailwind classes', () => {
      expect(cn('px-4', 'px-8')).toBe('px-8');
    });

    it('should handle empty values', () => {
      expect(cn('', undefined, null, 'valid-class')).toBe('valid-class');
    });
  });
});