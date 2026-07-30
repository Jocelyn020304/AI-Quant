"""
生成 Task 1 共享静态 K 线数据（Tencent 格式），供 Task 1/2/3/4 统一离线调用。
输出: Task 1/kline_static.json
格式: { "stocks": { "sh600519": [[date,O,C,H,L,V], ...], ... } }
日期范围: 2022-01-01 ~ 2024-12-31（与既有 48 只保持一致）
"""
import json, os, time, urllib.request

OUT = os.path.join(os.path.dirname(__file__), 'kline_static.json')

# 合并 Task 1 / Task 2 / Task 3 内置列表的所有代码（已修正已知笔误）
A_SHARE = [
    # 沪市主板
    '600519','600036','601318','601012','600900','601899','600585','601888','600016',
    '601166','600000','601398','601288','601988','601668','600309','601088','600276',
    '600809','600887','600104','600196','603259','603501','600028','600030','600031',
    '600048','600150','600690','601127','601138','601328','601628','601633','601688',
    '601728','601766','601857','601919','601939','601985',
    # 深市主板
    '000001','000002','000333','000651','000568','000858','002475','002594','002230',
    '002142','000725','002304','002352','002415','000100','002371','002129','000063',
    '002714','000002','002714',
    # 创业板
    '300750','300059','300122','300274','300003','300760','300015','300124','300142',
    '300308','301269',
    # 科创板
    '688256','688981','688111','688041','688012','688005','688036','688187','688303',
    '688239','688169','688271',
]
HK = ['00700','09988','09888','09618','09999','03690','01810','02015','09868','09866','02382','01211']

def to_front(code):
    if code.startswith('6') or code.startswith('9'):
        return 'sh' + code
    if code.startswith('0') or code.startswith('3'):
        return 'sz' + code
    if code.startswith('4') or code.startswith('8'):
        return 'bj' + code
    return 'sh' + code

def fetch_kline(front, start='2022-01-01', end='2024-12-31'):
    url = (f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
           f'?param={front},day,{start},{end},800,qfq')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read().decode('utf-8'))
    node = d.get('data', {}).get(front, {})
    klines = node.get('qfqday') or node.get('day') or []
    return klines

result = {}
failed = []
codes = list(dict.fromkeys(A_SHARE)) + ['hk' + c for c in HK]  # dedupe, keep order
for raw in codes:
    if raw.startswith('hk'):
        front = raw
    else:
        front = to_front(raw)
    try:
        kl = fetch_kline(front)
        if not kl:
            failed.append(front); continue
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
        print(f'  {front}: {len(arr)} bars')
    except Exception as e:
        failed.append(front)
        print(f'  {front}: FAIL {e}')
    time.sleep(0.05)

output = {
    '_meta': {'generated': 'static-tencent', 'stock_count': len(result),
              'range': '2022-01-01~2024-12-31', 'format': 'tencent_kline'},
    'stocks': result,
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

size_kb = os.path.getsize(OUT) / 1024
print(f'\n✅ 生成完毕: {OUT}')
print(f'   成功 {len(result)} 只, 失败 {len(failed)} 只, 大小 {size_kb:.0f} KB')
if failed:
    print('   失败列表:', failed)
