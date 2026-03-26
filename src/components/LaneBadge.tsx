import React from 'react';

type Lane = 'premium' | 'standard' | 'unassigned' | 'rejected' | null | undefined;

interface LaneBadgeProps {
  lane: Lane;
  size?: 'sm' | 'md';
}

const LaneBadge: React.FC<LaneBadgeProps> = ({ lane, size = 'md' }) => {
  if (!lane || lane === 'rejected') return null;

  const sizeClasses = size === 'sm'
    ? 'text-xs px-1.5 py-0.5'
    : 'text-xs px-2 py-1';

  if (lane === 'premium') {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full font-semibold ${sizeClasses} bg-emerald-100 text-emerald-800 border border-emerald-300`}>
        <span>⭐</span> PREMIUM
      </span>
    );
  }

  if (lane === 'standard') {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full font-semibold ${sizeClasses} bg-blue-100 text-blue-800 border border-blue-300`}>
        <span>📦</span> STANDARD
      </span>
    );
  }

  // unassigned
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${sizeClasses} bg-gray-100 text-gray-500 border border-gray-200`}>
      PENDING
    </span>
  );
};

export default LaneBadge;
