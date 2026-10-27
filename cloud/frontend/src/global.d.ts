// Global type declarations for TianLian V3

// AMap declarations
interface AMapOptions {
  center?: [number, number];
  zoom?: number;
  mapStyle?: string;
  [key: string]: any;
}

interface AMapMarkerOptions {
  position: [number, number];
  title?: string;
  icon?: any;
  label?: any;
  [key: string]: any;
}

declare class AMapMap {
  constructor(container: string | HTMLElement, opts?: AMapOptions);
  setZoomAndCenter(zoom: number, center: [number, number]): void;
  add(overlay: any): void;
  remove(overlay: any): void;
  clearMap(): void;
  destroy(): void;
  on(event: string, handler: (e: any) => void): void;
  getCenter(): { lng: number; lat: number };
  setCenter(center: [number, number]): void;
  setZoom(zoom: number): void;
  [key: string]: any;
}

declare class AMapMarker {
  constructor(opts?: AMapMarkerOptions);
  on(event: string, handler: (e: any) => void): void;
  getPosition(): { lng: number; lat: number };
  [key: string]: any;
}

declare namespace AMap {
  class Map extends AMapMap {}
  class Marker extends AMapMarker {}
}

interface Window {
  AMap: typeof AMap;
  _AMapSecurityConfig: { securityJsCode: string };
}
