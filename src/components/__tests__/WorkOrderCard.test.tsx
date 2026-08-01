import { TouchableOpacity } from 'react-native';
import { render, fireEvent } from '@testing-library/react-native';
import WorkOrderCard from '../WorkOrderCard';
import { WorkOrder } from '../../types';

const makeOrder = (overrides: Partial<WorkOrder> = {}): WorkOrder => ({
  id: 'WO-001',
  stationId: 1,
  stationName: '示范站',
  title: '充电桩离线排查',
  description: '桩A反复掉线',
  type: 'repair',
  priority: 'high',
  status: 'pending',
  assigneeId: 7,
  assigneeName: '王工',
  creatorId: 1,
  creatorName: '调度',
  createdAt: '2026-01-15T10:00:00Z',
  updatedAt: '2026-01-15T10:00:00Z',
  ...overrides,
});

describe('WorkOrderCard', () => {
  it('should render title, station and assignee', () => {
    const { getByText } = render(<WorkOrderCard order={makeOrder()} />);
    expect(getByText('充电桩离线排查')).toBeTruthy();
    expect(getByText('示范站')).toBeTruthy();
    expect(getByText('王工')).toBeTruthy();
  });

  it('should map known type to Chinese label', () => {
    const { getByText } = render(<WorkOrderCard order={makeOrder()} />);
    expect(getByText('维修')).toBeTruthy();
  });

  it('should fall back to raw type for unknown type', () => {
    const order = makeOrder({ type: 'deep_clean' as WorkOrder['type'] });
    const { getByText } = render(<WorkOrderCard order={order} />);
    expect(getByText('deep_clean')).toBeTruthy();
  });

  it('should show 未分配 when assigneeName missing', () => {
    const order = makeOrder({ assigneeId: undefined, assigneeName: undefined });
    const { getByText } = render(<WorkOrderCard order={order} />);
    expect(getByText('未分配')).toBeTruthy();
  });

  it('should show 暂无描述 when description empty', () => {
    const order = makeOrder({ description: '' });
    const { getByText } = render(<WorkOrderCard order={order} />);
    expect(getByText('暂无描述')).toBeTruthy();
  });

  it('should hide description in compact mode', () => {
    const order = makeOrder({ description: '桩A反复掉线' });
    const { queryByText } = render(<WorkOrderCard order={order} compact />);
    expect(queryByText('桩A反复掉线')).toBeNull();
  });

  it('should render created date', () => {
    const { getByText } = render(<WorkOrderCard order={makeOrder()} />);
    // zh-CN locale 格式如 2026/1/15
    expect(getByText(/2026\/1\/15/)).toBeTruthy();
  });

  it('should wrap in TouchableOpacity and call onPress with order', () => {
    const onPress = jest.fn();
    const order = makeOrder();
    const { UNSAFE_getByType } = render(
      <WorkOrderCard order={order} onPress={onPress} />
    );
    const touchable = UNSAFE_getByType(TouchableOpacity);
    fireEvent.press(touchable);
    expect(onPress).toHaveBeenCalledTimes(1);
    expect(onPress).toHaveBeenCalledWith(order);
  });

  it('should not be pressable without onPress', () => {
    const { UNSAFE_queryByType } = render(<WorkOrderCard order={makeOrder()} />);
    expect(UNSAFE_queryByType(TouchableOpacity)).toBeNull();
  });
});
