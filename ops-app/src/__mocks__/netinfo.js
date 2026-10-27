/**
 * Mock for @react-native-community/netinfo
 * Mapped via package.json jest.moduleNameMapper
 */
/* global jest */

const fetchImpl = jest.fn().mockResolvedValue({
  isConnected: true,
  isInternetReachable: true,
  type: 'wifi',
});
const unsubscribeFn = jest.fn();
const addEventListenerImpl = jest.fn().mockReturnValue(unsubscribeFn);

const netInfoMock = {
  fetch: fetchImpl,
  addEventListener: addEventListenerImpl,
};

module.exports = netInfoMock;
module.exports.default = netInfoMock;
