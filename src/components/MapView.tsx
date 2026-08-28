import React, { useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { Station } from '../types';
import { formatDistance } from '../utils/format';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

interface MapViewProps {
  stations: Station[];
  selectedStationId?: number;
  onStationPress?: (station: Station) => void;
  height?: number;
}

/**
 * MapView component for displaying charging stations on a map.
 *
 * NOTE: This is a simulated map placeholder.
 * In production, integrate with react-native-maps (Google Maps / Apple Maps)
 * or a web-based map component.
 *
 * The component renders a visual map-like grid showing station markers
 * arranged by their relative positions.
 */
const MapView: React.FC<MapViewProps> = ({
  stations,
  selectedStationId,
  onStationPress,
  height = 300,
}) => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  if (!stations || stations.length === 0) {
    return (
      <View style={[styles.container, { height }]}>
        <View style={styles.emptyMap}>
          <Text style={styles.emptyIcon}>🗺️</Text>
          <Text style={styles.emptyText}>暂无站点数据</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.container, { height }]}>
      {/* Map background */}
      <View style={styles.mapBackground}>
        {/* Grid lines */}
        {Array.from({ length: 4 }).map((_, i) => (
          <View
            key={`h-${i}`}
            style={[
              styles.gridLine,
              styles.gridLineHorizontal,
              { top: `${(i + 1) * 20}%` },
            ]}
          />
        ))}
        {Array.from({ length: 4 }).map((_, i) => (
          <View
            key={`v-${i}`}
            style={[
              styles.gridLine,
              styles.gridLineVertical,
              { left: `${(i + 1) * 20}%` },
            ]}
          />
        ))}

        {/* Map labels */}
        <Text style={styles.mapLabel}>N</Text>

        {/* Station markers */}
        {stations.map((station, index) => {
          const isSelected = station.id === selectedStationId;
          // Distribute stations across the map with some pseudo-random positioning
          const pos = getStationPosition(index, stations.length);
          return (
            <TouchableOpacity accessibilityRole="button"
              key={station.id}
              style={[
                styles.marker,
                {
                  left: `${pos.x}%`,
                  top: `${pos.y}%`,
                },
                isSelected && styles.markerSelected,
              ]}
              onPress={() => onStationPress?.(station)}
              activeOpacity={0.7}
            >
              <View
                style={[
                  styles.markerDot,
                  isSelected && styles.markerDotSelected,
                  {
                    borderColor: colors.primary,
                    backgroundColor:
                      station.availableConnectors > 0 ? colors.success : colors.error,
                  },
                ]}
              >
                <Text style={styles.markerIcon}>⚡</Text>
              </View>
              <Text
                style={[
                  styles.markerLabel,
                  isSelected && [
                    styles.markerLabelSelected,
                    { backgroundColor: colors.primary },
                  ],
                ]}
                numberOfLines={1}
              >
                {station.name}
              </Text>
              {station.distance !== undefined && (
                <Text style={styles.markerDistance}>
                  {formatDistance(station.distance)}
                </Text>
              )}
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Legend */}
      <View style={styles.legend}>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: '#2e7d32' }]} />
          <Text style={styles.legendText}>可用</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: '#c62828' }]} />
          <Text style={styles.legendText}>已满</Text>
        </View>
        <Text style={styles.legendCount}>
          {stations.length} 个站点
        </Text>
      </View>
    </View>
  );
};

/**
 * Distribute station markers in a grid-like pattern so they don't overlap.
 */
function getStationPosition(index: number, total: number): { x: number; y: number } {
  if (total <= 1) return { x: 50, y: 45 };

  // Arrange in a 3-column grid
  const cols = Math.min(3, total);
  const rows = Math.ceil(total / cols);
  const col = index % cols;
  const row = Math.floor(index / cols);

  // Add some offset so they're not perfectly aligned
  const xOffset = col === 0 ? 10 : col === 1 ? 5 : -5;
  const yOffset = row === 0 ? 5 : row === rows - 1 ? -5 : 0;

  return {
    x: 12 + (col * 32) + xOffset,
    y: 10 + (row * 28) + yOffset,
  };
}

const createStyles = (colors: ThemeColors) =>
  StyleSheet.create({
  container: {
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#e8f5e9',
  },
  emptyMap: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.pageBg,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 8,
  },
  emptyText: {
    fontSize: 14,
    color: colors.textSecondary,
  },
  mapBackground: {
    flex: 1,
    position: 'relative',
  },
  gridLine: {
    position: 'absolute',
    backgroundColor: 'rgba(0,0,0,0.06)',
  },
  gridLineHorizontal: {
    left: 0,
    right: 0,
    height: 1,
  },
  gridLineVertical: {
    top: 0,
    bottom: 0,
    width: 1,
  },
  mapLabel: {
    position: 'absolute',
    top: 4,
    right: 10,
    fontSize: 16,
    fontWeight: '700',
    color: 'rgba(0,0,0,0.3)',
  },
  marker: {
    position: 'absolute',
    alignItems: 'center',
    maxWidth: 100,
  },
  markerSelected: {
    zIndex: 10,
  },
  markerDot: {
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#fff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 4,
  },
  markerDotSelected: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 3,
  },
  markerIcon: {
    fontSize: 14,
  },
  markerLabel: {
    fontSize: 10,
    color: colors.textPrimary,
    fontWeight: '600',
    marginTop: 2,
    backgroundColor: 'rgba(255,255,255,0.9)',
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 2,
    overflow: 'hidden',
  },
  markerLabelSelected: {
    color: '#fff',
  },
  markerDistance: {
    fontSize: 9,
    color: colors.textSecondary,
    backgroundColor: 'rgba(255,255,255,0.8)',
    paddingHorizontal: 3,
    borderRadius: 2,
  },
  legend: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.9)',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginRight: 16,
  },
  legendDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 4,
  },
  legendText: {
    fontSize: 11,
    color: colors.textSecondary,
  },
  legendCount: {
    marginLeft: 'auto',
    fontSize: 11,
    color: colors.textSecondary,
    fontWeight: '500',
  },
});

export default MapView;