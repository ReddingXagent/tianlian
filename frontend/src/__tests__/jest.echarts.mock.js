// Mock echarts-for-react and echarts
jest.mock('echarts-for-react/lib/core', () => {
  return {
    __esModule: true,
    default: () => null,
  };
});
