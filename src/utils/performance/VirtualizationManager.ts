/**
 * VirtualizationManager - Handles large list virtualization and memory optimization
 * Implements efficient rendering for large datasets
 */

import React, { useMemo, useCallback, useState, useEffect, useRef } from 'react';
import { logger } from '@/utils/secureLogger';

export interface VirtualizationConfig {
  itemHeight: number;
  containerHeight: number;
  overscan: number;
  enableDynamicHeight: boolean;
}

export interface VirtualizedItem<T> {
  index: number;
  data: T;
  style: React.CSSProperties;
}

export class VirtualizationManager<T> {
  private config: VirtualizationConfig;
  private itemHeights: Map<number, number> = new Map();
  private scrollTop = 0;
  private containerRef: React.RefObject<HTMLDivElement>;

  constructor(config: VirtualizationConfig) {
    this.config = config;
    this.containerRef = React.createRef();
  }

  calculateVisibleRange(itemCount: number): { start: number; end: number } {
    const { itemHeight, containerHeight, overscan } = this.config;
    
    const startIndex = Math.max(0, Math.floor(this.scrollTop / itemHeight) - overscan);
    const endIndex = Math.min(
      itemCount - 1,
      Math.ceil((this.scrollTop + containerHeight) / itemHeight) + overscan
    );

    return { start: startIndex, end: endIndex };
  }

  getVirtualizedItems(data: T[], visibleRange: { start: number; end: number }): VirtualizedItem<T>[] {
    const items: VirtualizedItem<T>[] = [];
    
    for (let i = visibleRange.start; i <= visibleRange.end; i++) {
      if (i < data.length) {
        const top = this.getItemOffset(i);
        const height = this.getItemHeight(i);
        
        items.push({
          index: i,
          data: data[i],
          style: {
            position: 'absolute',
            top,
            left: 0,
            right: 0,
            height
          }
        });
      }
    }
    
    return items;
  }

  private getItemOffset(index: number): number {
    if (!this.config.enableDynamicHeight) {
      return index * this.config.itemHeight;
    }
    
    let offset = 0;
    for (let i = 0; i < index; i++) {
      offset += this.getItemHeight(i);
    }
    return offset;
  }

  private getItemHeight(index: number): number {
    if (this.config.enableDynamicHeight && this.itemHeights.has(index)) {
      return this.itemHeights.get(index)!;
    }
    return this.config.itemHeight;
  }

  setItemHeight(index: number, height: number): void {
    if (this.config.enableDynamicHeight) {
      this.itemHeights.set(index, height);
    }
  }

  getTotalHeight(itemCount: number): number {
    if (!this.config.enableDynamicHeight) {
      return itemCount * this.config.itemHeight;
    }
    
    let totalHeight = 0;
    for (let i = 0; i < itemCount; i++) {
      totalHeight += this.getItemHeight(i);
    }
    return totalHeight;
  }

  handleScroll(scrollTop: number): void {
    this.scrollTop = scrollTop;
  }

  scrollToIndex(index: number, itemCount: number): void {
    const offset = this.getItemOffset(index);
    if (this.containerRef.current) {
      this.containerRef.current.scrollTop = offset;
    }
  }

  getContainerRef(): React.RefObject<HTMLDivElement> {
    return this.containerRef;
  }
}

// React hook for virtualization
export const useVirtualization = <T>(
  data: T[],
  config: VirtualizationConfig
) => {
  const [scrollTop, setScrollTop] = useState(0);
  const manager = useMemo(() => new VirtualizationManager<T>(config), [config]);
  
  const visibleRange = useMemo(() => {
    manager.handleScroll(scrollTop);
    return manager.calculateVisibleRange(data.length);
  }, [manager, scrollTop, data.length]);
  
  const virtualizedItems = useMemo(() => {
    return manager.getVirtualizedItems(data, visibleRange);
  }, [manager, data, visibleRange]);
  
  const totalHeight = useMemo(() => {
    return manager.getTotalHeight(data.length);
  }, [manager, data.length]);
  
  const containerRef = manager.getContainerRef();
  
  const handleScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);
  
  const scrollToIndex = useCallback((index: number) => {
    manager.scrollToIndex(index, data.length);
  }, [manager, data.length]);
  
  const setItemHeight = useCallback((index: number, height: number) => {
    manager.setItemHeight(index, height);
  }, [manager]);
  
  return {
    virtualizedItems,
    totalHeight,
    containerRef,
    handleScroll,
    scrollToIndex,
    setItemHeight,
    visibleRange
  };
};

// Performance-optimized list component
export interface VirtualListProps<T> {
  data: T[];
  itemHeight: number;
  height: number;
  renderItem: (item: VirtualizedItem<T>) => React.ReactNode;
  overscan?: number;
  onItemHeightChange?: (index: number, height: number) => void;
}

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