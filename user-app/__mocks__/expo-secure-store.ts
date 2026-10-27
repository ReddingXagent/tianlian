// Mock for expo-secure-store
const store: Record<string, string> = {};

export const getItemAsync = jest.fn(async (key: string): Promise<string | null> => {
  return store[key] ?? null;
});

export const setItemAsync = jest.fn(async (key: string, value: string): Promise<void> => {
  store[key] = value;
});

export const deleteItemAsync = jest.fn(async (key: string): Promise<void> => {
  delete store[key];
});

export function __clearMockStore() {
  Object.keys(store).forEach((key) => delete store[key]);
}