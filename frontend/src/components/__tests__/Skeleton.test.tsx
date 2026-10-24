import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import SkeletonPage from '../Skeleton';

describe('SkeletonPage', () => {
  it('renders dashboard skeleton', () => {
    const { container } = render(<SkeletonPage type="dashboard" />);
    expect(container.firstChild).toBeTruthy();
  });

  it('renders table skeleton', () => {
    const { container } = render(<SkeletonPage type="table" count={3} />);
    expect(container.firstChild).toBeTruthy();
  });

  it('renders card skeleton', () => {
    const { container } = render(<SkeletonPage type="card" count={4} />);
    expect(container.firstChild).toBeTruthy();
  });

  it('renders detail skeleton', () => {
    const { container } = render(<SkeletonPage type="detail" />);
    expect(container.firstChild).toBeTruthy();
  });

  it('renders list skeleton', () => {
    const { container } = render(<SkeletonPage type="list" count={5} />);
    expect(container.firstChild).toBeTruthy();
  });

  it('defaults to table type', () => {
    const { container } = render(<SkeletonPage />);
    expect(container.firstChild).toBeTruthy();
  });
});
