"""
生成各 Task 共享的静态 K 线数据（Tencent 行情接口，无需 token），供
Task 1/2/3/4 统一离线调用。

输出: 每个 Task 目录下各一份 kline_static.json
格式: { "stocks": { "sh600519": [[date,O,C,H,L,V], ...], ... } }
日期范围: 2022-01-01 ~ 今天（每次运行自动刷新到最新交易日）

设计要点（用于 GitHub Actions 自动刷新）:
  1. 结束日期动态取当天，数据始终最新
  2. 先读取已有 kline_static.json 作为兜底；某只股票抓取失败时保留旧数据
     （避免网络抖动导致港股等数据丢失）
  3. 仅用标准库（urllib），无需 pip 安装依赖，CI 环境直接可跑
  4. 抓取带重试；写入全部 4 个 Task 目录，保证看板一致
"""
import json
import os
import time
import datetime
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))          # .../Task 1
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)                       # 项目根
TASK_DIRS = [os.path.join(PROJECT_ROOT, f'Task {i}') for i in (1, 2, 3, 4)]

START = '2022-01-01'
END = datetime.date.today().isoformat()                          # 动态结束日期
COUNT = 2000                                                     # 足够覆盖 2022~今

# 合并 Task 1 / Task 2 / Task 3 内置列表的所有代码（已修正已知笔误）
A_SHARE = [
    # 沪市主板
    '600519', '600036', '601318', '601012', '600900', '601899', '600585', '601888',
    '600016', '601166', '600000', '601398', '601288', '601988', '601668', '600309',
    '601088', '600276', '600809', '600887', '600104', '600196', '603259', '603501',
    '600028', '600030', '600031', '600048', '600150', '600690', '601127', '601138',
    '601328', '601628', '601633', '601688', '601728', '601766', '601857', '601919',
    '601939', '601985',
    # 深市主板
    '000001', '000002', '000333', '000651', '000568', '000858', '002475', '002594',
    '002230', '002142', '000725', '002304', '002352', '002415', '000100', '002371',
    '002129', '000063', '002714',
    # 创业板
    '300750', '300059', '300122', '300274', '300003', '300760', '300015', '300124',
    '300142', '300308', '301269',
    # 科创板
    '688256', '688981', '688111', '688041', '688012', '688005', '688036', '688187',
    '688303', '688239', '688169', '688271',
]
HK = ['00700', '09988', '09888', '09618', '09999', '03690', '01810', '02015',
      '09868', '09866', '02382', '01211']


def to_front(code):
    if code.startswith('6') or code.startswith('9'):
        return 'sh' + code
    if code.startswith('0') or code.startswith('3'):
        return 'sz' + code
    if code.startswith('4') or code.startswith('8'):
        return 'bj' + code
    return 'sh' + code


def fetch_kline(front, retries=3):
    url = (f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
           f'?param={front},day,{START},{END},{COUNT},qfq')
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode('utf-8'))
            node = d.get('data', {}).get(front, {})
            klines = node.get('qfqday') or node.get('day') or []
            if not klines:
                last_err = f'空数据(node keys={list(node.keys())})'
                time.sleep(0.3 * (attempt + 1))
                continue
            return klines
        except Exception as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    print(f'  {front}: FAIL 重试{retries}次后仍失败 -> {last_err}')
    return None


def load_old():
    """读取首个存在的旧文件作为兜底数据"""
    for d in TASK_DIRS:
        p = os.path.join(d, 'kline_static.json')
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding='utf-8')).get('stocks', {})
            except Exception:
                pass
    return {}


def main():
    old = load_old()
    result = dict(old)  # 先填旧数据，成功的会被覆盖，失败的保留
    failed = []

    codes = list(dict.fromkeys(A_SHARE)) + ['hk' + c for c in HK]  # 去重保序
    print(f'开始刷新 {len(codes)} 只股票, 范围 {START}~{END}')

    for raw in codes:
        front = raw if raw.startswith('hk') else to_front(raw)
        try:
            kl = fetch_kline(front)
            if kl is None:
                failed.append(front)
                continue
            arr = []
            for k in kl:
                arr.append([
                    k[0].replace('-', ''),
                    round(float(k[1]), 2),
                    round(float(k[2]), 2),
                    round(float(k[3]), 2),
                    round(float(k[4]), 2),
                    int(float(k[5])),
                ])
            result[front] = arr
            if front in old:
                print(f'  {front}: 更新 {len(arr)} bars')
            else:
                print(f'  {front}: 新增 {len(arr)} bars')
        except Exception as e:
            failed.append(front)
            print(f'  {front}: 异常 {e}')
        time.sleep(0.05)

    output = {
        '_meta': {
            'generated': datetime.date.today().isoformat(),
            'stock_count': len(result),
            'range': f'{START}~{END}',
            'format': 'tencent_kline',
        },
        'stocks': result,
    }

    written = []
    for d in TASK_DIRS:
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, 'kline_static.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, separators=(',', ':'))
        written.append(p)

    size_kb = os.path.getsize(written[0]) / 1024
    print(f'\n✅ 生成完毕, 共写入 {len(written)} 个文件')
    print(f'   总计 {len(result)} 只, 本次失败 {len(failed)} 只, 单文件大小 {size_kb:.0f} KB')
    if failed:
        print('   失败列表(已保留旧数据):', failed)


if __name__ == '__main__':
    main()
