/**
 * Type declaration for optional @react-native-community/netinfo dependency.
 * The hook dynamically imports it and gracefully degrades when not installed.
 */
declare module '@react-native-community/netinfo' {
  export interface NetInfoState {
    isConnected: boolean | null;
    isInternetReachable: boolean | null;
    type: string;
    details?: unknown;
    isExpensive?: boolean;
  }
  export type NetInfoSubscription = () => void;
  export type NetInfoChangeHandler = (state: NetInfoState) => void;
  interface NetInfo {
    fetch: (requestedInterface?: string) => Promise<NetInfoState>;
    addEventListener: (listener: NetInfoChangeHandler) => NetInfoSubscription;
  }
  const defaultExport: NetInfo;
  export default defaultExport;
}
