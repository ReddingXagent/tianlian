// F1217: 全量jest抖动修复 — RNTL默认asyncUtilTimeout=1000ms在冷缓存/负载竞争下不够用
// (F1197源码级归因, 触发条件"CI频繁抖动"已于F1216轮4跑2败达成, 修复候选兑现)
// 详见: F1197 user-app同模式归因 (8核92套件冷缓存竞争+级联waitFor链)
import { configure } from '@testing-library/react-native';

configure({ asyncUtilTimeout: 4000 });
