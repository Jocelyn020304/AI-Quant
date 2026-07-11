"""使用Tushare API获取宁德时代和茅台日线数据并保存为CSV"""
import tushare as ts
import pandas as pd
import os

TOKEN = 'your_token_here'
ts.set_token(TOKEN)
pro = ts.pro_api()

OUT_DIR = r'C:\Users\Administrator\Desktop\量化交易：AI大模型辅助的金融交易策略\Task 3\stock_data'
os.makedirs(OUT_DIR, exist_ok=True)

for code, name in [('300750.SZ', '宁德时代'), ('600519.SH', '贵州茅台')]:
    try:
        df = pro.daily(ts_code=code, start_date='20250701', end_date='20260709')
        df = df.sort_values('trade_date').reset_index(drop=True)
        fpath = os.path.join(OUT_DIR, f'{name}_日线数据.csv')
        df.to_csv(fpath, index=False, encoding='utf-8-sig')
        print(f'✅ {name}: {len(df)}条记录 → {fpath}')
    except Exception as e:
        print(f'⚠️ {name} 获取失败: {e}')
