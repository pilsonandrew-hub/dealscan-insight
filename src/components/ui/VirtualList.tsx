/**
 * VirtualList - Performance-optimized React component for large lists
 * Uses VirtualizationManager for efficient rendering
 */

import React, { useMemo, useEffect, useRef, useCallback } from 'react';
import { 
  useVirtualization, 
  VirtualListProps, 
  VirtualizationConfig,
  VirtualizedItem 
} from '@/utils/performance/VirtualizationManager';

export const VirtualList = <T,>({
  data,
  itemHeight,
  height,
  renderItem,
  overscan = 5,
  onItemHeightChange
}: VirtualListProps<T>) => {
  const config = useMemo<VirtualizationConfig>(() => ({
    itemHeight,
    containerHeight: height,
    overscan,
    enableDynamicHeight: !!onItemHeightChange
  }), [itemHeight, height, overscan, onItemHeightChange]);
  
  const {
    virtualizedItems,
    totalHeight,
    containerRef,
    handleScroll,
    setItemHeight
  } = useVirtualization(data, config);
  
  // Handle dynamic height measurement
  const itemRefs = useRef<Map<number, HTMLElement>>(new Map());
  
  useEffect(() => {
    if (onItemHeightChange) {
      virtualizedItems.forEach(({ index }) => {
        const element = itemRefs.current.get(index);
        if (element) {
          const rect = element.getBoundingClientRect();
          if (rect.height !== itemHeight) {
            setItemHeight(index, rect.height);
            onItemHeightChange(index, rect.height);
          }
        }
      });
    }
  }, [virtualizedItems, itemHeight, onItemHeightChange, setItemHeight]);
  
  const setItemRef = useCallback((index: number, element: HTMLElement | null) => {
    if (element) {
      itemRefs.current.set(index, element);
    } else {
      itemRefs.current.delete(index);
    }
  }, []);
  
  return (
    <div
      ref={containerRef}
      style={{
        height,
        overflow: 'auto',
        position: 'relative'
      }}
      onScroll={handleScroll}
    >
      <div style={{ height: totalHeight, position: 'relative' }}>
        {virtualizedItems.map((item) => (
          <div
            key={item.index}
            style={item.style}
            ref={(el) => setItemRef(item.index, el)}
          >
            {renderItem(item)}
          </div>
        ))}
      </div>
    </div>
  );
};

export default VirtualList;